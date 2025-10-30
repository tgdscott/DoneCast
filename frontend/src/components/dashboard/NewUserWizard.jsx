import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from "@/hooks/use-toast";
import { makeApi, buildApiUrl } from '@/lib/apiClient';
import { CheckCircle, ArrowLeft, X, HelpCircle } from 'lucide-react';

const WizardStep = ({ children }) => <div className="py-4">{children}</div>;

const INITIAL_FORM = {
  podcastName: '',
  podcastDescription: '',
  coverArt: null,
};

const NewUserWizard = ({ open, onOpenChange, token, onPodcastCreated }) => {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState(() => ({ ...INITIAL_FORM }));
  const { toast } = useToast();

  const skipCloseConfirmRef = useRef(false);

  const resetWizard = useCallback(() => {
    setStep(1);
    setFormData(() => ({ ...INITIAL_FORM }));
  }, []);

  const hasUnsaved = useMemo(() => {
    const nameFilled = formData.podcastName.trim().length > 0;
    const descFilled = formData.podcastDescription.trim().length > 0;
    return step > 1 || nameFilled || descFilled || !!formData.coverArt;
  }, [formData, step]);

  const wizardSteps = [
    { id: 'welcome', title: 'Welcome' },
    { id: 'showDetails', title: 'About your show' },
    { id: 'coverArt', title: 'Podcast Cover Art (optional)' },
    { id: 'finish', title: 'All set' },
  ];
  const totalSteps = wizardSteps.length;
  const stepId = wizardSteps[step - 1]?.id;

  const nextStep = () => setStep((prev) => Math.min(prev + 1, totalSteps));
  const prevStep = () => setStep((prev) => Math.max(prev - 1, 1));

  const handleChange = (e) => {
    const { id, value, files } = e.target;
    setFormData((prev) => ({ ...prev, [id]: files ? files[0] : value }));
  };


  useEffect(() => {
    if (!open || !hasUnsaved || typeof window === 'undefined') return;
    const handleBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [open, hasUnsaved]);

  const handleDialogOpenChange = (nextOpen) => {
    if (nextOpen) {
      onOpenChange(true);
      return;
    }
    if (skipCloseConfirmRef.current) {
      skipCloseConfirmRef.current = false;
      onOpenChange(false);
      resetWizard();
      return;
    }
    if (hasUnsaved) {
      const confirmLeave = typeof window !== 'undefined' ? window.confirm('Leave the setup wizard? Your details will be lost.') : true;
      if (!confirmLeave) {
        return;
      }
    }
    onOpenChange(false);
    resetWizard();
  };

  const handleFinish = async () => {
    try {
      const podcastPayload = new FormData();
      podcastPayload.append('name', formData.podcastName);
      podcastPayload.append('description', formData.podcastDescription);
      if (formData.coverArt) {
        podcastPayload.append('cover_image', formData.coverArt);
      }

      const podcastRes = await makeApi(token).raw('/api/podcasts/', { method: 'POST', body: podcastPayload });
      if (podcastRes && podcastRes.status && podcastRes.status >= 400) { const errorData = podcastRes; throw new Error(errorData.detail || 'Failed to create the podcast show.'); }
      const newPodcast = podcastRes;

  toast({ title: "Great!", description: "Your new podcast show has been created." });
      onPodcastCreated(newPodcast); // Pass the new podcast object back to the parent

    } catch (error) {
      toast({ title: "An Error Occurred", description: error.message, variant: "destructive" });
    } finally {
      skipCloseConfirmRef.current = true;
      onOpenChange(false);
      resetWizard();
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleDialogOpenChange}>
      <DialogContent className="sm:max-w-[550px]">
        <DialogHeader className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => handleDialogOpenChange(false)}
              className="flex items-center gap-1 text-muted-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <DialogTitle className="flex-1 text-center">Let's Create Your First Podcast!</DialogTitle>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => handleDialogOpenChange(false)}
              aria-label="Close setup"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground text-center">Step {step} of {totalSteps}</p>
        </DialogHeader>

  {stepId === 'welcome' && (
          <WizardStep>
            <h3 className="text-lg font-semibold mb-2">Welcome</h3>
            <p className="text-sm text-gray-600">
              We'll guide you one step at a time. Don't worry about breaking anything, and we're going to save as you go.
            </p>
          </WizardStep>
        )}

  {stepId === 'showDetails' && (
          <WizardStep>
            <h3 className="text-lg font-semibold mb-2">About your show</h3>
            <DialogDescription className="mb-4">
              Tell us the name and what it's about. You can change this later.
            </DialogDescription>
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="podcastName" className="text-right">Name</Label>
                <Input id="podcastName" value={formData.podcastName} onChange={handleChange} className="col-span-3" placeholder="e.g., 'The Morning Cup'" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="podcastDescription" className="text-right">Description</Label>
                <Textarea id="podcastDescription" value={formData.podcastDescription} onChange={handleChange} className="col-span-3" placeholder="e.g., 'A daily podcast about the latest tech news.'" />
              </div>
            </div>
          </WizardStep>
        )}

  {stepId === 'coverArt' && (
          <WizardStep>
            <h3 className="text-lg font-semibold mb-2">Cover art</h3>
            <DialogDescription className="mb-2">
              Upload a square image (at least 1400x1400). We'll preview how it looks.
            </DialogDescription>
            <p className="text-xs text-gray-500 mb-4">No artwork yet? You can skip and add it later.</p>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="coverArt" className="text-right">Image</Label>
              <Input id="coverArt" type="file" onChange={handleChange} className="col-span-3" accept="image/png, image/jpeg" />
            </div>
          </WizardStep>
        )}



  {stepId === 'finish' && (
          <WizardStep>
            <h3 className="text-lg font-semibold mb-2">All set</h3>
            <p className="text-sm text-gray-600 mb-1">Nice work. You can publish now or explore your dashboard first.</p>
            <p className="text-xs text-gray-500">There's a short tour on the next screen if you'd like it.</p>
          </WizardStep>
        )}

        <DialogFooter>
          {step > 1 && <Button variant="outline" onClick={prevStep}>Back</Button>}
          {step < totalSteps && <Button onClick={nextStep}>Continue</Button>}
          {step === totalSteps && <Button onClick={handleFinish}>Finish</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default NewUserWizard;













