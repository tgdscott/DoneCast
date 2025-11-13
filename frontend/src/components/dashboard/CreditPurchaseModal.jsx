import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { makeApi, isApiError } from '@/lib/apiClient';
import { AlertCircle, Loader2 } from 'lucide-react';

export default function CreditPurchaseModal({ 
  open, 
  onOpenChange, 
  token, 
  planKey,
  requiredCredits,
  onSuccess 
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handlePurchase = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const api = makeApi(token);
      const data = await api.post('/api/billing/checkout/addon_credits', {
        plan_key: planKey || 'pro',
        return_url: window.location.pathname,
      });
      
      // Open checkout in popup
      const w = window.open(data.url, 'ppp_stripe_checkout_credits', 'width=720,height=850,noopener');
      if (!w) {
        // Fallback: navigate current tab
        window.location.href = data.url;
      } else {
        w.focus();
        
        // Poll for checkout completion
        const checkInterval = setInterval(() => {
          try {
            if (w.closed) {
              clearInterval(checkInterval);
              // Check if purchase was successful by refreshing usage
              // The webhook will add credits, so we can check after a short delay
              setTimeout(() => {
                if (onSuccess) {
                  onSuccess();
                }
                onOpenChange(false);
              }, 2000);
            }
          } catch (e) {
            // Cross-origin check failed, window might still be open
          }
        }, 500);
        
        // Cleanup after 5 minutes
        setTimeout(() => {
          clearInterval(checkInterval);
        }, 300000);
      }
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Purchase Additional Credits</DialogTitle>
          <DialogDescription>
            You need more credits to complete this episode assembly. Purchase additional credits to continue.
          </DialogDescription>
        </DialogHeader>
        
        <div className="py-4">
          {requiredCredits && (
            <div className="mb-4 p-3 bg-blue-50 rounded-lg">
              <p className="text-sm text-gray-700">
                <strong>Credits needed:</strong> {requiredCredits.toLocaleString()}
              </p>
            </div>
          )}
          
          <p className="text-sm text-gray-600 mb-4">
            Additional credits never expire and can be used anytime. They will be added to your account immediately after purchase.
          </p>
          
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}
        </div>
        
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            onClick={handlePurchase}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Opening Checkout...
              </>
            ) : (
              'Purchase Credits'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}




