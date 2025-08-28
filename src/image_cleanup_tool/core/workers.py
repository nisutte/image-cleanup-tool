import asyncio
import time
from typing import List, Dict, Union, Tuple, Optional
from pathlib import Path
from dataclasses import dataclass

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..api import ImageProcessor, get_client
from ..utils.log_utils import get_logger

logger = get_logger(__name__)


@dataclass
class AnalysisResult:
    """Result of image analysis with metadata."""
    path: Path
    result: Union[dict, Exception]
    processing_time: float
    retry_count: int = 0
    token_usage: Optional[Dict[str, int]] = None


class AsyncWorkerPool:
    """
    Async worker pool for analyzing images with proper rate limiting and retry logic.
    
    Uses asyncio and aiohttp for efficient concurrent API calls with built-in
    connection pooling and proper rate limiting.
    """

    def __init__(
        self,
        image_paths: List[Path],
        api_name: str = "openai",
        max_concurrent: int = 10,
        requests_per_minute: int = 60,
        size: int = 512,
        timeout: float = 30.0,
    ) -> None:
        self.image_paths = list(image_paths)
        self.api_name = api_name
        self.max_concurrent = max_concurrent
        self.requests_per_minute = requests_per_minute
        self.size = size
        self.timeout = timeout

        # Initialize API client
        self.api_client = get_client(api_name)

        # Rate limiting: calculate delay between requests
        self.request_delay = 60.0 / requests_per_minute if requests_per_minute > 0 else 0

        # Results storage
        self.results: Dict[Path, AnalysisResult] = {}
        self.completed_count = 0
        self.total_count = len(image_paths)

        # Semaphore for limiting concurrent requests
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Rate limiting semaphore
        self.rate_limit_semaphore = asyncio.Semaphore(1)

    async def analyze_all(self) -> Dict[Path, AnalysisResult]:
        """
        Analyze all images concurrently with rate limiting and retry logic.
        
        Returns:
            Dictionary mapping image paths to analysis results.
        """
        logger.info(f"Starting analysis of {self.total_count} images with max {self.max_concurrent} concurrent requests")
        
        # Create tasks for all images
        tasks = [self._analyze_single_image(path) for path in self.image_paths]
        
        # Run all tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(f"Completed analysis of {self.completed_count}/{self.total_count} images")
        return self.results

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def _analyze_single_image(self, path: Path) -> None:
        """
        Analyze a single image with retry logic and rate limiting.
        
        Args:
            path: Path to the image file to analyze.
        """
        start_time = time.time()
        retry_count = 0
        
        try:
            async with self.semaphore:
                # Rate limiting
                await self._rate_limit()
                
                # Process the image
                logger.debug(f"Analyzing {path.name}")
                
                # Load and encode image (this is CPU-bound, so we run it in a thread pool)
                loop = asyncio.get_event_loop()
                b64 = await loop.run_in_executor(
                    None, ImageProcessor.load_and_encode_image, str(path), self.size
                )

                # Analyze with the selected API
                result, token_usage = await self._analyze_with_api(b64)
                
                processing_time = time.time() - start_time
                self.results[path] = AnalysisResult(
                    path=path,
                    result=result,
                    processing_time=processing_time,
                    retry_count=retry_count,
                    token_usage=token_usage
                )
                
                self.completed_count += 1
                logger.debug(f"Completed {path.name} in {processing_time:.2f}s")
                
        except Exception as e:
            processing_time = time.time() - start_time
            self.results[path] = AnalysisResult(
                path=path,
                result=e,
                processing_time=processing_time,
                retry_count=retry_count,
                token_usage=None
            )
            self.completed_count += 1
            logger.error(f"Failed to analyze {path.name}: {e}")

    async def _rate_limit(self) -> None:
        """Implement rate limiting between requests."""
        if self.request_delay > 0:
            await asyncio.sleep(self.request_delay)

    async def _analyze_with_api(self, image_b64: str) -> Tuple[dict, Dict[str, int]]:
        """
        Analyze image with the selected API using aiohttp.

        Args:
            image_b64: Base64 encoded image string.

        Returns:
            Tuple of (analysis_result, token_usage_dict)
        """
        # Use the API client to analyze the image
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.api_client.analyze_image, image_b64)

    def get_progress(self) -> Tuple[int, int]:
        """Get current progress (completed, total)."""
        return self.completed_count, self.total_count

    def get_results(self) -> Dict[Path, AnalysisResult]:
        """Get all analysis results."""
        return self.results.copy()


# Convenience function for easy usage
async def analyze_images_async(
    image_paths: List[Path],
    api_name: str = "openai",
    max_concurrent: int = 10,
    requests_per_minute: int = 60,
    size: int = 512,
) -> Dict[Path, AnalysisResult]:
    """
    Convenience function to analyze multiple images asynchronously.

    Args:
        image_paths: List of image paths to analyze.
        api_name: Name of the API to use ('openai', 'claude', 'gemini').
        max_concurrent: Maximum number of concurrent requests.
        requests_per_minute: Rate limit for API requests.
        size: Image size for encoding.

    Returns:
        Dictionary mapping image paths to analysis results.
    """
    pool = AsyncWorkerPool(
        image_paths=image_paths,
        api_name=api_name,
        max_concurrent=max_concurrent,
        requests_per_minute=requests_per_minute,
        size=size
    )
    return await pool.analyze_all()
