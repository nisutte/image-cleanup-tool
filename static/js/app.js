// Global variables
let cacheData = null;
let currentImageIndex = 0;
let imageEntries = [];
let filteredEntries = [];
let currentFilter = null;

// DOM elements
const currentImage = document.getElementById('current-image');
const imageLoading = document.getElementById('image-loading');
const imageError = document.getElementById('image-error');
const imagePath = document.getElementById('image-path');
const imageHash = document.getElementById('image-hash');
const imageCounter = document.getElementById('image-counter');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');

// Filter elements
const modelFilter = document.getElementById('model-filter');
const classificationFilter = document.getElementById('classification-filter');
const percentageFilter = document.getElementById('percentage-filter');
const applyFilterBtn = document.getElementById('apply-filter');
const clearFilterBtn = document.getElementById('clear-filter')
const filterStatus = document.getElementById('filter-status');
const filterText = document.getElementById('filter-text');
const resultsCount = document.getElementById('results-count');

// Initialize the application
async function init() {
    try {
        await loadCacheData();
        setupEventListeners();
        initializeFilters();
        showCurrentImage();
    } catch (error) {
        console.error('Failed to initialize app:', error);
        showError('Failed to load application data');
    }
}

// Load cache data from API
async function loadCacheData() {
    const response = await fetch('/api/cache');
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    cacheData = await response.json();
    imageEntries = Object.entries(cacheData.entries);

    if (imageEntries.length === 0) {
        throw new Error('No images found in cache');
    }

    console.log(`Loaded ${imageEntries.length} images from cache`);

    // Initialize filtered entries with all images
    filteredEntries = [...imageEntries];
}

// Set up event listeners
function setupEventListeners() {
    prevBtn.addEventListener('click', showPreviousImage);
    nextBtn.addEventListener('click', showNextImage);

    // Filter event listeners
    applyFilterBtn.addEventListener('click', applyFilter);
    clearFilterBtn.addEventListener('click', clearFilter);

    // Allow Enter key to apply filter from percentage input
    percentageFilter.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            applyFilter();
        }
    });

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') {
            showPreviousImage();
        } else if (e.key === 'ArrowRight') {
            showNextImage();
        }
    });
}

// Initialize filters
function initializeFilters() {
    // Filters are already initialized with default values in HTML
    updateFilterStatus();
}

// Apply current filter
function applyFilter() {
    const model = modelFilter.value;
    const classification = classificationFilter.value;
    const minPercentage = parseInt(percentageFilter.value) || 0;

    currentFilter = {
        model: model,
        classification: classification,
        minPercentage: minPercentage
    };

    // Filter the entries
    filteredEntries = imageEntries.filter(([hash, entry]) => {
        return matchesFilter(entry, currentFilter);
    });

    // Reset to first filtered image
    currentImageIndex = 0;

    // Update UI
    updateFilterStatus();
    showCurrentImage();

    console.log(`Applied filter: ${filteredEntries.length} results`);
}

// Check if an entry matches the current filter
function matchesFilter(entry, filter) {
    const { model, classification, minPercentage } = filter;
    const sizes = [256, 512, 768, 1024];

    if (model === 'any') {
        // Check if any model and any size meets the criteria
        const models = ['gemini', 'claude', 'openai'];
        return models.some(modelName => {
            return sizes.some(size => {
                const modelKey = `${modelName}_${size}`;
                const modelData = entry.models[modelKey] || entry.models[modelName]; // Fallback to legacy format
                if (!modelData || !modelData.result || !modelData.result.final_classification) {
                    return false;
                }
                return modelData.result.final_classification[classification] >= minPercentage;
            });
        });
    } else {
        // Check specific model across all sizes
        return sizes.some(size => {
            const modelKey = `${model}_${size}`;
            const modelData = entry.models[modelKey] || entry.models[model]; // Fallback to legacy format
            if (!modelData || !modelData.result || !modelData.result.final_classification) {
                return false;
            }
            return modelData.result.final_classification[classification] >= minPercentage;
        });
    }
}

// Clear filter
function clearFilter() {
    currentFilter = null;
    filteredEntries = [...imageEntries];
    currentImageIndex = 0;

    updateFilterStatus();
    showCurrentImage();

    console.log('Filter cleared');
}

// Update filter status display
function updateFilterStatus() {
    if (currentFilter) {
        const modelName = currentFilter.model === 'any' ? 'Any Model' :
                         currentFilter.model.charAt(0).toUpperCase() + currentFilter.model.slice(1);
        const className = currentFilter.classification.charAt(0).toUpperCase() + currentFilter.classification.slice(1);

        filterText.textContent = `${modelName} - ${className} ≥ ${currentFilter.minPercentage}%`;
        resultsCount.textContent = `${filteredEntries.length} of ${imageEntries.length} images`;

        filterStatus.style.display = 'flex';
    } else {
        filterStatus.style.display = 'none';
    }
}

// Show the current image and its analysis
function showCurrentImage() {
    if (filteredEntries.length === 0) {
        // No filtered results
        imagePath.textContent = 'No images match filter criteria';
        imageHash.textContent = '';
        currentImage.style.display = 'none';
        imageLoading.style.display = 'none';
        imageError.style.display = 'block';
        imageError.textContent = 'No images match the current filter. Try adjusting your criteria.';
        clearModelOverviews();
        return;
    }

    const [hash, entry] = filteredEntries[currentImageIndex];

    // Update navigation
    updateNavigation();

    // Update image info
    imagePath.textContent = entry.path;
    imageHash.textContent = `Hash: ${hash}`;

    // Load and display image
    loadImage(entry.path);

    // Update model comparisons
    updateModelComparisons(entry);
}

// Load image from server
function loadImage(imagePath) {
    // Hide current content
    currentImage.style.display = 'none';
    imageError.style.display = 'none';
    imageLoading.style.display = 'block';

    // Set image source
    currentImage.src = `/images/${imagePath}`;

    // Handle load events
    currentImage.onload = () => {
        imageLoading.style.display = 'none';
        currentImage.style.display = 'block';
    };

    currentImage.onerror = () => {
        imageLoading.style.display = 'none';
        imageError.style.display = 'block';
        imageError.textContent = 'Failed to load image';
    };
}

// Update navigation buttons and counter
function updateNavigation() {
    const total = filteredEntries.length;
    const current = currentImageIndex + 1;

    imageCounter.textContent = `${current} / ${total}`;
    prevBtn.disabled = currentImageIndex === 0;
    nextBtn.disabled = currentImageIndex === total - 1;
}

// Navigate to previous image
function showPreviousImage() {
    if (currentImageIndex > 0) {
        currentImageIndex--;
        showCurrentImage();
    }
}

// Navigate to next image
function showNextImage() {
    if (currentImageIndex < filteredEntries.length - 1) {
        currentImageIndex++;
        showCurrentImage();
    }
}

// Update model comparison display for all sizes
function updateModelComparisons(entry) {
    const models = ['gemini', 'claude', 'openai'];
    const sizes = [256, 512, 768, 1024];

    sizes.forEach(size => {
        models.forEach(model => {
            // Try size-specific key first, then fallback to legacy format
            const modelKey = `${model}_${size}`;
            const modelData = entry.models[modelKey] || entry.models[model];

            if (modelData && modelData.result) {
                updateModelOverview(model, size, modelData.result);
            } else {
                clearModelOverview(model, size);
            }
        });
    });
}

// Update a specific model's overview for a specific size
function updateModelOverview(modelName, size, result) {
    const overview = document.getElementById(`${modelName}-${size}-overview`);

    if (result.final_classification) {
        // Update keep score bar
        updateScoreBar(overview, 'keep', result.final_classification.keep);

        // Update discard score bar
        updateScoreBar(overview, 'discard', result.final_classification.discard);

        // Update unsure score bar
        updateScoreBar(overview, 'unsure', result.final_classification.unsure);
    }
}

// Helper function to update a score bar
function updateScoreBar(overview, type, score) {
    const containers = overview.querySelectorAll('.score-bar-container');
    let targetContainer = null;

    // Find the correct container based on the type
    containers.forEach(container => {
        const label = container.querySelector('.score-label');
        if (label) {
            const labelText = label.textContent.toLowerCase();
            if (labelText === type) {
                targetContainer = container;
            }
        }
    });

    if (!targetContainer) return;

    const fill = targetContainer.querySelector(`.${type}-fill`);
    const text = targetContainer.querySelector('.score-text');

    if (fill && text) {
        fill.style.width = `${score}%`;
        fill.setAttribute('data-score', score);
        text.textContent = `${score}%`;
    }
}

// Clear all model overviews for all sizes
function clearModelOverviews() {
    const models = ['gemini', 'claude', 'openai'];
    const sizes = [256, 512, 768, 1024];

    sizes.forEach(size => {
        models.forEach(modelName => {
            clearModelOverview(modelName, size);
        });
    });
}

// Clear a model overview when no data is available
function clearModelOverview(modelName, size) {
    const overview = document.getElementById(`${modelName}-${size}-overview`);

    // Clear score bars
    ['keep', 'discard', 'unsure'].forEach(type => {
        updateScoreBar(overview, type, 0);
    });
}



// Show error message
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.style.cssText = 'color: #e74c3c; text-align: center; padding: 20px; font-size: 1.2rem;';
    errorDiv.textContent = message;

    document.querySelector('.container').prepend(errorDiv);
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', init);
