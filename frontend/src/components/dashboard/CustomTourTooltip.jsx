import React from 'react';
import { Button } from "@/components/ui/button";

export const CustomTourTooltip = ({
    index,
    step,
    tooltipProps,
    backProps,
    primaryProps,
    isLastStep,
    size,
}) => {
    return (
        <div
            {...tooltipProps}
            className="bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-6 max-w-md mx-4 md:mx-0 border border-gray-100"
            style={{ minWidth: '320px' }}
        >
            {/* Image Area - Only render if step has an image */}
            {step.image && (
                <div className="w-full aspect-video bg-gray-50 rounded-xl overflow-hidden border border-gray-100 shadow-inner">
                    <img
                        src={step.image}
                        alt={step.title}
                        className="w-full h-full object-cover"
                    />
                </div>
            )}

            <div className="text-center space-y-3">
                <h3 className="text-2xl font-bold text-gray-900 tracking-tight">{step.title}</h3>
                <p className="text-gray-500 text-sm leading-relaxed font-medium">
                    {step.content}
                </p>
            </div>

            <div className="flex items-center justify-between pt-2">
                {/* Back Button */}
                <div className="w-24">
                    {index > 0 && (
                        <Button
                            variant="outline"
                            onClick={backProps.onClick}
                            className="w-full rounded-lg border-gray-200 hover:bg-gray-50 hover:text-gray-900 text-gray-600 font-medium h-10"
                        >
                            Back
                        </Button>
                    )}
                </div>

                {/* Progress Dots */}
                <div className="flex gap-2">
                    {Array.from({ length: size }).map((_, i) => (
                        <div
                            key={i}
                            className={`h-2 w-2 rounded-full transition-all duration-300 ${i === index ? 'bg-gray-900 scale-110' : 'bg-gray-200'
                                }`}
                        />
                    ))}
                </div>

                {/* Next/Finish Button */}
                <div className="w-24">
                    <Button
                        onClick={primaryProps.onClick}
                        className="w-full rounded-lg bg-gray-900 hover:bg-gray-800 text-white font-medium h-10 shadow-lg shadow-gray-900/10"
                    >
                        {isLastStep ? 'Finish' : 'Next'}
                    </Button>
                </div>
            </div>
        </div>
    );
};

export default CustomTourTooltip;
