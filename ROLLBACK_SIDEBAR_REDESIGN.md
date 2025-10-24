# Rollback Instructions - Template Editor Sidebar Redesign

## Date: October 19, 2024

## Backup Files Created

All original files backed up with `.backup-oct19-2024` extension:

1. `TemplateEditor.jsx.backup-oct19-2024` - Main editor component
2. `TemplateBasicsCard.jsx.backup-oct19-2024` - Basics card component
3. `EpisodeStructureCard.jsx.backup-oct19-2024` - Structure card component
4. `MusicTimingSection.jsx.backup-oct19-2024` - Music/timing card component
5. `AIGuidanceCard.jsx.backup-oct19-2024` - AI guidance card component

## New Files Created (for sidebar redesign)

These files will be created during the redesign:

### Layout Components
- `layout/TemplateEditorLayout.jsx`
- `layout/TemplateEditorSidebar.jsx`
- `layout/TemplatePageWrapper.jsx`

### Page Components
- `pages/TemplateBasicsPage.jsx`
- `pages/TemplateSchedulePage.jsx`
- `pages/TemplateAIPage.jsx`
- `pages/TemplateStructurePage.jsx`
- `pages/TemplateMusicPage.jsx`
- `pages/TemplateAdvancedPage.jsx`

## How to Rollback (If Needed)

### Quick Rollback (PowerShell)

```powershell
# Navigate to template editor directory
cd d:\PodWebDeploy\frontend\src\components\dashboard\template-editor

# Restore original files
Copy-Item "TemplateEditor.jsx.backup-oct19-2024" "TemplateEditor.jsx" -Force
Copy-Item "TemplateBasicsCard.jsx.backup-oct19-2024" "TemplateBasicsCard.jsx" -Force
Copy-Item "EpisodeStructureCard.jsx.backup-oct19-2024" "EpisodeStructureCard.jsx" -Force
Copy-Item "MusicTimingSection.jsx.backup-oct19-2024" "MusicTimingSection.jsx" -Force
Copy-Item "AIGuidanceCard.jsx.backup-oct19-2024" "AIGuidanceCard.jsx" -Force

# Remove new sidebar files
Remove-Item -Path "layout" -Recurse -Force
Remove-Item -Path "pages" -Recurse -Force

Write-Host "Rollback complete! Old template editor restored."
```

### Or Use This Script

I've also created a rollback script at:
`d:\PodWebDeploy\scripts\rollback_template_sidebar.ps1`

Just run:
```powershell
.\scripts\rollback_template_sidebar.ps1
```

## Git Rollback (Alternative)

If you want to use Git instead:

```powershell
# See what changed
git diff frontend/src/components/dashboard/template-editor/

# Discard all changes to template editor
git checkout -- frontend/src/components/dashboard/template-editor/

# Or revert specific commit
git revert <commit-hash>
```

## Testing After Rollback

1. Start frontend dev server
2. Navigate to template editor
3. Verify old UI appears (all cards stacked vertically)
4. Test creating/editing template
5. Test guided tour

## When to Rollback

**Immediate rollback if:**
- Template editor completely broken
- Can't save templates
- Critical features not working
- Production users reporting major issues

**Fix forward if:**
- Minor UI glitches
- Tour steps need adjustment
- Small bugs that can be fixed quickly
- Non-critical features affected

## Backup Location

All backup files are in:
`d:\PodWebDeploy\frontend\src\components\dashboard\template-editor\*.backup-oct19-2024`

**Do NOT delete these files** until sidebar redesign is proven stable (at least 2 weeks in production).

## Support

If you need to rollback:
1. Run the rollback script
2. Restart frontend dev server
3. Test thoroughly
4. Document what went wrong
5. Review implementation plan before trying again

---

**Created**: October 19, 2024  
**Backup verified**: ✅ Yes  
**Rollback tested**: Pending (will test after changes made)
