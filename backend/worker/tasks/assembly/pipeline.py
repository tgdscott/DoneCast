from abc import ABC, abstractmethod
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

# Define the context type that gets passed between pipeline steps
PipelineContext = Dict[str, Any]

class PipelineStep(ABC):
    """
    Abstract Base Class for a single, distinct operation in the Assembly Pipeline.
    """
    def __init__(self, step_name: str):
        self.step_name = step_name

    @abstractmethod
    def run(self, context: PipelineContext) -> PipelineContext:
        """
        Executes the step's logic and returns the updated context.
        Must be implemented by all concrete steps.
        """
        pass

class AssemblyPipeline:
    """
    Manages the execution flow of the podcast assembly process.
    """
    def __init__(self, steps: List[PipelineStep]):
        self.steps = steps
        self.context: PipelineContext = {}

    def run(self, initial_context: PipelineContext) -> PipelineContext:
        """
        Runs all steps sequentially, passing the context from one to the next.
        """
        self.context = initial_context
        for step in self.steps:
            logger.info(f"--- Running Step: {step.step_name} ---")
            try:
                self.context = step.run(self.context)
            except Exception as e:
                logger.error(f"Error in {step.step_name}: {e}", exc_info=True)
                # Log error, potentially handle cleanup, and re-raise or fail gracefully
                raise
        return self.context
