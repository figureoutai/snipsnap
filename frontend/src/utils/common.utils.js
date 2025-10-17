export function isValidVideoURL(url) {
    // Basic URL validation
    try {
        new URL(url);
        // Check if URL ends with common video extensions
        return /\.(mp4|mkv|avi|mov|wmv|flv)$/i.test(url);
    } catch {
        return false;
    }
};