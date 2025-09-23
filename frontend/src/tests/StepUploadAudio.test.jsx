import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StepUploadAudio from '@/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx';

describe('StepUploadAudio step controls', () => {
  const baseFile = new File(['audio'], 'episode.mp3', { type: 'audio/mpeg' });
  const noop = () => {};
  const ref = { current: null };

  it('keeps Continue disabled until automation answers are provided', () => {
    const handleNext = vi.fn();
    const handleEdit = vi.fn();

    render(
      <StepUploadAudio
        uploadedFile={baseFile}
        isUploading={false}
        onFileChange={noop}
        fileInputRef={ref}
        onBack={noop}
        onNext={handleNext}
        onEditAutomations={handleEdit}
        canProceed={false}
        pendingIntentLabels={['Flubber']}
      />
    );

    expect(screen.getByText(/We still need your answer/i)).toBeInTheDocument();
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    expect(continueBtn).toBeDisabled();

    const answerBtn = screen.getByRole('button', { name: /answer now/i });
    fireEvent.click(answerBtn);
    expect(handleEdit).toHaveBeenCalledTimes(1);
    expect(handleNext).not.toHaveBeenCalled();
  });

  it('enables Continue and invokes onNext once answers are complete', () => {
    const handleNext = vi.fn();

    render(
      <StepUploadAudio
        uploadedFile={baseFile}
        isUploading={false}
        onFileChange={noop}
        fileInputRef={ref}
        onBack={noop}
        onNext={handleNext}
        onEditAutomations={noop}
        canProceed={true}
        pendingIntentLabels={[]}
      />
    );

    expect(screen.getByText(/Automation answers saved/i)).toBeInTheDocument();
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    expect(continueBtn).not.toBeDisabled();
    fireEvent.click(continueBtn);
    expect(handleNext).toHaveBeenCalledTimes(1);
  });
});
