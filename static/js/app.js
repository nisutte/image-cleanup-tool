// Global variables
let cacheData = null;
let currentImageIndex = 0;
let imageEntries = [];

// DOM elements
const currentImage = document.getElementById('current-image');
const imageLoading = document.getElementById('image-loading');
const imageError = document.getElementById('image-error');
const imagePath = document.getElementById('image-path');
const imageHash = document.getElementById('image-hash');
const imageCounter = document.getElementById('image-counter');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');

// Initialize the application
async function init() {
    try {
        await loadCacheData();
        setupEventListeners();
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
}

// Set up event listeners
function setupEventListeners() {
    prevBtn.addEventListener('click', showPreviousImage);
    nextBtn.addEventListener('click', showNextImage);

    // Details toggle button
    const toggleBtn = document.getElementById('toggle-details');
    const detailsPanel = document.querySelector('.details-panel');
    const detailsContent = document.querySelector('.details-content');

    toggleBtn.addEventListener('click', () => {
        const isCollapsed = detailsPanel.classList.contains('collapsed');

        if (isCollapsed) {
            detailsPanel.classList.remove('collapsed');
            detailsPanel.classList.add('expanded');
            detailsContent.style.display = 'block';
            toggleBtn.innerHTML = '<span class="toggle-icon">▲</span> Hide Details';
        } else {
            detailsPanel.classList.remove('expanded');
            detailsPanel.classList.add('collapsed');
            detailsContent.style.display = 'none';
            toggleBtn.innerHTML = '<span class="toggle-icon">▼</span> Show Details';
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

// Show the current image and its analysis
function showCurrentImage() {
    if (imageEntries.length === 0) return;

    const [hash, entry] = imageEntries[currentImageIndex];

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
    const total = imageEntries.length;
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
    if (currentImageIndex < imageEntries.length - 1) {
        currentImageIndex++;
        showCurrentImage();
    }
}

// Update model comparison display
function updateModelComparisons(entry) {
    const models = ['gemini', 'claude', 'openai'];

    models.forEach(model => {
        const modelData = entry.models[model];
        if (modelData && modelData.result) {
            updateModelOverview(model, modelData.result);
            updateModelSection(model, modelData.result);
        } else {
            clearModelOverview(model);
            clearModelSection(model);
        }
    });
}

// Update a specific model's overview in the top section
function updateModelOverview(modelName, result) {
    const overview = document.getElementById(`${modelName}-overview`);

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

// Clear a model overview when no data is available
function clearModelOverview(modelName) {
    const overview = document.getElementById(`${modelName}-overview`);

    // Clear score bars
    ['keep', 'discard', 'unsure'].forEach(type => {
        updateScoreBar(overview, type, 0);
    });
}

// Update a specific model's section
function updateModelSection(modelName, result) {
    const section = document.getElementById(`${modelName}-section`);

    // Update category scores
    const categoriesContainer = section.querySelector(`#${modelName}-categories`);
    categoriesContainer.innerHTML = '';

    if (result.category_scores) {
        Object.entries(result.category_scores).forEach(([category, score]) => {
            const categoryItem = document.createElement('div');
            categoryItem.className = 'category-item';

            const label = document.createElement('span');
            label.className = 'category-label';
            label.textContent = formatCategoryName(category);

            const value = document.createElement('span');
            value.className = 'category-value';
            value.textContent = `${score}%`;

            categoryItem.appendChild(label);
            categoryItem.appendChild(value);
            categoriesContainer.appendChild(categoryItem);
        });
    }

    // Update description
    const description = section.querySelector(`#${modelName}-description`);
    description.textContent = result.description || 'No description available';

    // Update reasoning
    const reasoning = section.querySelector(`#${modelName}-reasoning`);
    reasoning.textContent = result.reasoning || 'No reasoning provided';
}

// Clear a model section when no data is available
function clearModelSection(modelName) {
    const section = document.getElementById(`${modelName}-section`);

    // Clear categories
    section.querySelector(`#${modelName}-categories`).innerHTML = '<div class="category-item"><span class="category-label">No data available</span></div>';

    // Clear description and reasoning
    section.querySelector(`#${modelName}-description`).textContent = 'No data available';
    section.querySelector(`#${modelName}-reasoning`).textContent = 'No data available';
}

// Format category names for display
function formatCategoryName(category) {
    const nameMap = {
        'blurry': 'Blurry',
        'meme': 'Meme',
        'screenshot': 'Screenshot',
        'document': 'Document',
        'personal': 'Personal',
        'non_personal': 'Non-Personal',
        'contains_faces': 'Contains Faces'
    };

    return nameMap[category] || category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
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
