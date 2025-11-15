import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import StepUploadAudio from '@/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx';

describe('StepUploadAudio step controls', () => {
  const baseFile = new File(['audio'], 'episode.mp3', { type: 'audio/mpeg' });
  const noop = () => {};
  const composeResolved = () => Promise.resolve();
  const ref = { current: null };
  const baseSegments = [{ id: 'seg-1', friendlyName: 'Intro', processingMode: 'standard' }];

  it('prompts for automation answers before continuing', () => {
    const handleNext = vi.fn();
    const handleEdit = vi.fn();

    render(
      <StepUploadAudio
        mainSegments={baseSegments}
        uploadedFilename="gs://test/file.wav"
        isUploading={false}
        onFileChange={noop}
        onSegmentRemove={noop}
        onSegmentProcessingChange={noop}
        composeSegments={composeResolved}
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
        mainSegments={baseSegments}
        uploadedFilename="gs://test/file.wav"
        isUploading={false}
        onFileChange={noop}
        onSegmentRemove={noop}
        onSegmentProcessingChange={noop}
        composeSegments={composeResolved}
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
