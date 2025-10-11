# Cover Image Padding Color Selection Feature

## Overview
Added the ability to choose between white or black padding color when using the "Pad" mode for cover images. This addresses the issue where grey play buttons appeared on YouTube thumbnails with the previous white-only padding.

## Changes Made

### File: `frontend/src/components/dashboard/CoverCropper.jsx`

#### 1. Added Padding Color State (Lines ~20-23)
```javascript
const [paddingColor, setPaddingColor] = useState(()=>{
  try { return localStorage.getItem('ppp_cover_padding_color') || 'white'; } catch { return 'white'; }
}); // 'white' | 'black'
```

#### 2. Updated Preview Canvas to Use Selected Color (Line ~157)
```javascript
// Use selected padding color
ctx.fillStyle = paddingColor === 'black' ? '#000000' : '#FFFFFF';
ctx.fillRect(0,0,200,200);
```

#### 3. Updated Export Canvas to Use Selected Color (Line ~181)
```javascript
// Paint selected padding color background for JPEG
ctx.fillStyle = paddingColor === 'black' ? '#000000' : '#FFFFFF';
ctx.fillRect(0,0,outSize,outSize);
```

#### 4. Added Persistence to localStorage (Line ~212)
```javascript
useEffect(()=>{ 
  try { localStorage.setItem('ppp_cover_padding_color', paddingColor); } catch {} 
},[paddingColor]);
```

#### 5. Added UI Controls for Padding Color Selection (Lines ~260-265)
Added buttons to select white or black padding color when in "Pad" mode:
- White button: Standard white background with blue highlight when selected
- Black button: Black background with white text, blue ring when selected
- Updated description text to show selected color dynamically

## User Experience

### Behavior
1. **Default**: White padding (matches previous behavior)
2. **Persistence**: User's choice is saved to localStorage (`ppp_cover_padding_color`)
3. **Per-User Setting**: Each user's browser remembers their last choice
4. **Visibility**: Color selector only appears when "Pad" mode is active

### UI Location
The padding color selector appears in the CoverCropper component:
1. Below the Crop/Pad mode buttons
2. Only visible when "Pad" mode is selected
3. Shows two buttons: "White" and "Black"
4. Updates the description text to reflect current selection

### Use Cases
- **White Padding**: Best for light-colored images, maintains traditional podcast cover look
- **Black Padding**: Ideal for dark-themed images, prevents grey play buttons on YouTube thumbnails

## Technical Details

### Canvas Rendering
- Preview canvas (200x200): Uses selected padding color for background
- Export canvas (up to 2048x2048): Uses selected padding color for JPEG background
- Color applied before drawing the centered image to ensure clean backgrounds

### Storage
- Key: `ppp_cover_padding_color`
- Values: `'white'` | `'black'`
- Location: Browser localStorage
- Scope: Per-browser, per-user

### Compatibility
- Works with existing crop/pad mode system
- No changes to backend API or database schema required
- Fully client-side feature

## Testing Recommendations

1. **Basic Functionality**
   - Upload an image
   - Switch to "Pad" mode
   - Toggle between white and black padding
   - Verify preview shows correct color
   - Save and verify exported image has correct padding color

2. **Persistence**
   - Select black padding
   - Refresh page
   - Upload new image and select pad mode
   - Verify black is still selected

3. **Visual Quality**
   - Test with light images on black padding
   - Test with dark images on white padding
   - Verify no color bleeding or artifacts
   - Check YouTube thumbnail appearance with both colors

4. **Edge Cases**
   - Try with very small images
   - Try with very large images
   - Verify crop mode is unaffected by padding color setting
   - Test localStorage disabled/private browsing

## Related Issues

This feature addresses the user's concern:
> "When dealing with images and crop/pad, if padding, I want to be able to choose a white pad or a black pad. The grey that the system spits out, especially if I'm using it for a YouTube thumbnail, or things like that, makes the play button look grey instead of the proper colors."

The feature provides:
- ✅ Choice between white and black padding
- ✅ Defaults to white (previous behavior)
- ✅ Remembers last choice
- ✅ Simple, intuitive UI
- ✅ Solves YouTube thumbnail play button issue
