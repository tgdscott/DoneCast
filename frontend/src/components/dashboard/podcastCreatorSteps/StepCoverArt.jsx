import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { FileImage, Upload, ArrowLeft } from 'lucide-react';
import CoverCropper from '../CoverCropper';

export default function StepCoverArt({
  episodeDetails,
  coverArtInputRef,
  coverCropperRef,
  coverNeedsUpload,
  isUploadingCover,
  onCoverFileSelected,
  onCoverCropChange,
  onCoverModeChange,
  onRemoveCover,
  onBack,
  onSkip,
  onContinue,
}) {
  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 4: Cover Art</CardTitle>
      </CardHeader>
      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-8 space-y-6">
          <div className="space-y-4">
            {!episodeDetails.coverArt && !episodeDetails.coverArtPreview && (
              <div
                className="border-2 border-dashed rounded-xl p-10 text-center"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (event.dataTransfer.files?.[0]) {
                    onCoverFileSelected(event.dataTransfer.files[0]);
                  }
                }}
              >
                <FileImage className="w-16 h-16 mx-auto text-gray-400" />
                <p className="mt-4 text-gray-600">Drag &amp; drop a cover image or click below.</p>
                <Button className="mt-4" variant="outline" onClick={() => coverArtInputRef.current?.click()}>
                  <Upload className="w-4 h-4 mr-2" />Choose Image
                </Button>
                <input
                  ref={coverArtInputRef}
                  type="file"
                  accept="image/*"
                  onChange={(event) => onCoverFileSelected(event.target.files?.[0])}
                  className="hidden"
                />
                <p className="text-xs text-gray-500 mt-4">Recommended: ≥1400x1400 JPG/PNG.</p>
              </div>
            )}

            {episodeDetails.coverArt && !episodeDetails.coverArtPreview && (
              <div className="space-y-4">
                <CoverCropper
                  ref={coverCropperRef}
                  sourceFile={episodeDetails.coverArt}
                  existingUrl={null}
                  value={episodeDetails.cover_crop}
                  onChange={onCoverCropChange}
                  onModeChange={onCoverModeChange}
                />
                <div className="flex gap-2 flex-wrap">
                  <Button size="sm" variant="outline" onClick={() => coverArtInputRef.current?.click()}>
                    <Upload className="w-4 h-4 mr-1" />Replace
                  </Button>
                  <Button size="sm" variant="ghost" onClick={onRemoveCover}>
                    Remove
                  </Button>
                  {coverNeedsUpload && <span className="text-xs text-amber-600 font-medium">Will upload on Continue</span>}
                </div>
              </div>
            )}

            {episodeDetails.coverArtPreview && (
              <div className="flex flex-col md:flex-row gap-10 items-start">
                <div className="w-48 h-48 rounded-lg overflow-hidden border bg-gray-50">
                  <img src={episodeDetails.coverArtPreview} alt="Cover preview" className="w-full h-full object-cover" />
                </div>
                <div className="space-y-3 text-sm">
                  <p className="text-gray-600">
                    Square cover uploaded
                    {episodeDetails.cover_image_path && (
                      <>
                        {' '}
                        as <span className="text-green-600">{episodeDetails.cover_image_path}</span>
                      </>
                    )}
                    .
                  </p>
                  <div className="flex gap-2 flex-wrap">
                    <Button size="sm" variant="outline" onClick={() => coverArtInputRef.current?.click()}>
                      <Upload className="w-4 h-4 mr-1" />Replace
                    </Button>
                    <Button size="sm" variant="ghost" onClick={onRemoveCover}>
                      Remove
                    </Button>
                  </div>
                  <input
                    ref={coverArtInputRef}
                    type="file"
                    accept="image/*"
                    onChange={(event) => onCoverFileSelected(event.target.files?.[0])}
                    className="hidden"
                  />
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
      <div className="flex justify-between pt-8">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back
        </Button>
        <div className="flex gap-3">
          <Button onClick={onSkip} variant="outline" size="lg">
            Skip
          </Button>
          <Button
            onClick={onContinue}
            size="lg"
            disabled={isUploadingCover}
            className="px-8 py-3 text-lg font-semibold text-white disabled:opacity-70"
            style={{ backgroundColor: '#2C3E50' }}
          >
            {coverNeedsUpload ? 'Upload & Continue' : 'Continue'}
            <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
          </Button>
        </div>
      </div>
    </div>
  );
}
