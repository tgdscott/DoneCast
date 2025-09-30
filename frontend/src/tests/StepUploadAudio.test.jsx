import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StepUploadAudio from '@/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx';

describe('StepUploadAudio step controls', () => {
  const baseFile = new File(['audio'], 'episode.mp3', { type: 'audio/mpeg' });
  const noop = () => {};
  const ref = { current: null };

  it('prompts for automation answers before continuing', () => {
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
        pendingIntentLabels={['Flubber']}
      />
    );

    expect(screen.getByText(/We need your answer/i)).toBeInTheDocument();
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    expect(continueBtn).not.toBeDisabled();
    fireEvent.click(continueBtn);
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
        pendingIntentLabels={[]}
      />
    );

    expect(screen.getByText(/These answers are saved automatically/i)).toBeInTheDocument();
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    expect(continueBtn).not.toBeDisabled();
    fireEvent.click(continueBtn);
    expect(handleNext).toHaveBeenCalledTimes(1);
  });
});
