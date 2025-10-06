# Episode Numbering Duplicate Fix

## Problem

Current behavior **blocks** episode assembly/update if season+episode number already exists:
- User creates Episode 1 with S1E1
- Needs to create NEW Episode 2 as S1E1 (will delete old one after)
- System **blocks** assembly with 409 error
- User stuck - can't proceed

## Solution

**Soft warning** instead of hard block:

### 1. Allow Duplicate Creation/Update
- Remove `raise HTTPException(409)` from assembly and update endpoints
- Set warning flag on episode: `has_numbering_conflict: bool`
- Log warning but allow processing to continue

### 2. Block NEW Episode Creation If Duplicates Exist
- Before allowing `/episodes` POST (new episode start), check for conflicts
- If ANY episode in podcast has `has_numbering_conflict=True`, return 409 with message:
  ```json
  {
    "code": "RESOLVE_DUPLICATE_NUMBERING",
    "message": "You have episodes with duplicate season/episode numbers. Please resolve these conflicts before creating new episodes.",
    "conflicts": [
      {"id": "uuid", "title": "Episode 1", "season": 1, "episode": 1},
      {"id": "uuid", "title": "Episode 2", "season": 1, "episode": 1}
    ]
  }
  ```

### 3. Frontend UX
- Show warning banner if `has_numbering_conflict` detected
- Disable "Create New Episode" button with tooltip
- Allow editing existing episodes to fix numbering
- Allow deleting conflicting episodes
- Once resolved, flag cleared automatically

## Implementation

### Database Migration
```sql
ALTER TABLE episode ADD COLUMN has_numbering_conflict BOOLEAN DEFAULT FALSE;
```

### Validation Flow
```
User Updates Episode → Check for duplicates → If found:
  - Set has_numbering_conflict=True on ALL matching episodes
  - Log warning
  - Allow save to proceed
  
User Creates New Episode → Check podcast for any has_numbering_conflict=True → If found:
  - Return 409 with conflict list
  - Block creation
  - Frontend shows resolution UI
```

### Resolution
1. User edits one of the conflicting episodes (changes numbering)
2. On save, check if conflict still exists
3. If resolved, clear `has_numbering_conflict` flag on all previously conflicting episodes

## Benefits
- ✅ Allows "create new, delete old" workflow
- ✅ Prevents podcast corruption (can't create MORE conflicts)
- ✅ Clear user feedback about what needs fixing
- ✅ Non-blocking for urgent workflows
