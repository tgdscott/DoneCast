# INTERN COMMAND BUG FIX - November 5, 2025

## THE ACTUAL PROBLEM

User **DID** mark Intern commands in the UI (screenshot proof provided).  
Frontend **DID** save the `intern_overrides` to `aiFeatures.intents`.  
BUT assembly received **EMPTY** `intern_overrides` because of wrong variable passed.

## ROOT CAUSE

**File**: `frontend/src/components/dashboard/hooks/usePodcastCreator.js` Line 159

```javascript
const assembly = useEpisodeAssembly({
  // ... other params
  intents: aiOrchestration.intents,  // ❌ WRONG - this is always empty!
  // Should be:
  // intents: aiFeatures.intents,    // ✅ CORRECT - has user's intern_overrides
});
```

**The Bug:**
- `aiFeatures.intents` contains the user-marked intern commands (`intern_overrides` array)
- `aiOrchestration.intents` is a SEPARATE state variable that's never updated with intern overrides
- Assembly was receiving `aiOrchestration.intents` which was always `{ ..., intern_overrides: [] }`

**Why this happened:**
- Code refactoring split AI features into two hooks: `useAIFeatures` and `useAIOrchestration`
- Both hooks maintain separate `intents` state
- `useAIOrchestration.intents` handles auto-detection ("did we detect intern keyword?")
- `useAIFeatures.intents` handles user-reviewed overrides (actual marked commands)
- Assembly was accidentally wired to the wrong one

## THE FIX

Changed line 159 from:
```javascript
intents: aiOrchestration.intents,
```

To:
```javascript
intents: aiFeatures.intents, // FIXED: Use aiFeatures.intents (has intern_overrides) not aiOrchestration.intents
```

## SECONDARY FIXES ALREADY APPLIED

1. **Proper buffer timing**: 500ms after marked endpoint (was 120ms)
2. **Silence padding**: 500ms before + 500ms after AI response (was none)
3. **Better error logging**: Shows why audio wasn't inserted
4. **Foreign key fix**: MediaTranscript deletion before MediaItem

## COPILOT INSTRUCTIONS UPDATED

Added crystal clear documentation:
- **FLUBBER = DELETE/CUT audio** (removes mistakes)
- **INTERN = INSERT/ADD audio** (adds AI responses)
- These are OPPOSITE operations
- NEVER confuse them

## FILES MODIFIED

1. `frontend/src/components/dashboard/hooks/usePodcastCreator.js` - Fixed intents source
2. `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py` - Buffer timing
3. `backend/api/services/audio/ai_intern.py` - Silence padding + logging
4. `backend/worker/tasks/assembly/orchestrator.py` - Foreign key fix
5. `.github/copilot-instructions.md` - Clarified Flubber vs Intern

## WHAT WILL HAPPEN NOW

When you mark Intern commands:
1. Frontend saves them to `aiFeatures.intents.intern_overrides`
2. Assembly receives `aiFeatures.intents` (not the empty aiOrchestration one)
3. Backend processes your marked commands with:
   - Insertion at your marked endpoint + 500ms
   - 500ms silence before AI response
   - AI response audio
   - 500ms silence after AI response
4. Total insertion: ~1 second + response duration

## APOLOGY

You were right. You DID mark the commands. The code was broken and wasn't sending them.  
This was a critical bug introduced during hook refactoring that made Intern completely non-functional.  
The fix is simple but the impact was severe - your marked commands were being silently discarded.

My apologies for not catching this immediately and for suggesting you didn't mark the commands.
