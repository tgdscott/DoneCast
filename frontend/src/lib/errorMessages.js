/**
 * Utility functions for converting technical error messages into user-friendly ones
 */

/**
 * Converts API error objects into user-friendly error messages
 * @param {Error|Object} error - The error object from API call
 * @param {Object} options - Options for error handling
 * @param {string} options.context - Context of the error (e.g., 'upload', 'save', 'delete')
 * @param {string} options.fallback - Fallback message if error can't be parsed
 * @returns {Object} { title: string, description: string, action?: string }
 */
export function getUserFriendlyError(error, options = {}) {
  const { context = 'operation', fallback = 'Something went wrong. Please try again.' } = options;
  
  // Handle null/undefined
  if (!error) {
    return {
      title: 'Error',
      description: fallback
    };
  }

  // Extract error details
  const status = error?.status || error?.response?.status;
  const detail = error?.detail || error?.error || error?.message || String(error);
  const isApiError = typeof error === 'object' && (error.detail || error.error || error.message);

  // Network errors
  if (!status && (detail?.includes('fetch') || detail?.includes('network') || detail?.includes('Failed to fetch'))) {
    return {
      title: 'Connection Problem',
      description: 'Unable to connect to the server. Please check your internet connection and try again.',
      action: 'Check your internet connection'
    };
  }

  // HTTP status code handling
  switch (status) {
    case 400:
      // Bad request - try to extract validation errors
      if (typeof detail === 'string') {
        // Check for common validation messages
        if (detail.toLowerCase().includes('required')) {
          return {
            title: 'Missing Information',
            description: 'Please fill in all required fields.',
            action: 'Check the form and try again'
          };
        }
        if (detail.toLowerCase().includes('invalid') || detail.toLowerCase().includes('format')) {
          return {
            title: 'Invalid Format',
            description: detail.length > 100 ? 'The information you entered is not in the correct format.' : detail,
            action: 'Check your input and try again'
          };
        }
        // Use detail if it's user-friendly (short and clear)
        if (detail.length < 150 && !detail.includes('traceback') && !detail.includes('exception')) {
          return {
            title: 'Invalid Request',
            description: detail
          };
        }
      }
      return {
        title: 'Invalid Request',
        description: 'The information you provided is not valid. Please check your input and try again.',
        action: 'Review your input'
      };

    case 401:
      return {
        title: 'Session Expired',
        description: 'Your session has expired. Please sign in again to continue.',
        action: 'Refresh the page and sign in'
      };

    case 403:
      return {
        title: 'Access Denied',
        description: 'You don\'t have permission to perform this action.',
        action: 'Contact support if you believe this is an error'
      };

    case 404:
      return {
        title: 'Not Found',
        description: context === 'delete' 
          ? 'This item may have already been deleted.'
          : 'The requested item could not be found.',
        action: 'Refresh the page'
      };

    case 409:
      return {
        title: 'Conflict',
        description: 'This action conflicts with another operation. Please refresh and try again.',
        action: 'Refresh the page'
      };

    case 413:
      return {
        title: 'File Too Large',
        description: 'The file you\'re trying to upload is too large. Please use a smaller file.',
        action: 'Reduce file size and try again'
      };

    case 422:
      return {
        title: 'Validation Error',
        description: typeof detail === 'string' && detail.length < 150
          ? detail
          : 'The information you provided is not valid. Please check your input.',
        action: 'Review your input'
      };

    case 429:
      return {
        title: 'Too Many Requests',
        description: 'You\'re making requests too quickly. Please wait a moment and try again.',
        action: 'Wait a few seconds and try again'
      };

    case 500:
    case 502:
    case 503:
      return {
        title: 'Server Error',
        description: 'Our servers are experiencing issues. Please try again in a few moments.',
        action: 'Try again in a moment'
      };

    case 504:
      return {
        title: 'Request Timeout',
        description: 'The request took too long to complete. Please try again.',
        action: 'Try again'
      };

    default:
      // Try to extract user-friendly message from detail
      if (typeof detail === 'string') {
        // If detail looks technical (has stack trace, etc.), use fallback
        if (detail.includes('Traceback') || detail.includes('Exception') || detail.includes('at ')) {
          return {
            title: 'Error',
            description: fallback
          };
        }
        // If detail is short and clear, use it
        if (detail.length < 200 && !detail.includes('Error:') && !detail.includes('error:')) {
          return {
            title: 'Error',
            description: detail
          };
        }
      }
      
      return {
        title: 'Error',
        description: fallback
      };
  }
}

/**
 * Gets a user-friendly error message for specific contexts
 */
export const contextErrors = {
  upload: {
    title: 'Upload Failed',
    description: 'We couldn\'t upload your file. Please check your internet connection and try again.',
    action: 'Check connection and retry'
  },
  save: {
    title: 'Save Failed',
    description: 'Your changes couldn\'t be saved. Please try again.',
    action: 'Try saving again'
  },
  delete: {
    title: 'Delete Failed',
    description: 'We couldn\'t delete this item. Please try again.',
    action: 'Try again'
  },
  publish: {
    title: 'Publish Failed',
    description: 'We couldn\'t publish your episode. Please try again.',
    action: 'Try publishing again'
  },
  load: {
    title: 'Load Failed',
    description: 'We couldn\'t load this information. Please refresh the page.',
    action: 'Refresh the page'
  }
};




