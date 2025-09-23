import { useEffect, useRef, useState, useCallback, forwardRef, useImperativeHandle } from 'react';

/*
  CoverCropper
  Minimal dependency-free square cropper.
  Props:
    sourceFile: File | null
    existingUrl: string | null (used if no sourceFile)
    value: string | null   // 'x1,y1,x2,y2'
    onChange: (cropString) => void
    disabled?: boolean
*/
const CoverCropper = forwardRef(function CoverCropper({ sourceFile, existingUrl, value, onChange, disabled, onModeChange }, ref) {
  const imgRef = useRef(null);
  const containerRef = useRef(null);
  const [imgUrl, setImgUrl] = useState(null);
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const [crop, setCrop] = useState({ x: 0, y: 0, size: 0 }); // all in natural pixels
  const [mode, setMode] = useState(()=>{
    try { return localStorage.getItem('ppp_cover_mode') || 'crop'; } catch { return 'crop'; }
  }); // 'crop' | 'pad'
  const [dragging, setDragging] = useState(false);
  const dragOffset = useRef({ dx: 0, dy: 0 });
  const lastEmitted = useRef(null);

  // Load image URL
  useEffect(() => {
    if (sourceFile) {
      const url = URL.createObjectURL(sourceFile);
      setImgUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    setImgUrl(existingUrl || null);
  }, [sourceFile, existingUrl]);

  // When image loads, initialize crop (center square) or restore from value
  const handleImageLoad = useCallback(() => {
    const img = imgRef.current;
    if (!img) return;
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    setDims({ w, h });

    // If no new sourceFile (editing existing) we keep current crop string; only recalc on new upload
    if (!sourceFile && value) {
      const parts = value.split(',').map(p => parseFloat(p.trim()));
      if (parts.length === 4 && parts.every(n => !isNaN(n))) {
        const [x1, y1, x2, y2] = parts;
        const size = Math.min(w, h, Math.max(0, x2 - x1), Math.max(0, y2 - y1));
        setCrop({ x: Math.max(0, x1), y: Math.max(0, y1), size });
        return;
      }
    }
    if (sourceFile) {
      // New upload: auto-center largest square
      const size = Math.min(w, h);
      const x = (w - size) / 2;
      const y = (h - size) / 2;
      setCrop({ x, y, size });
    }
  }, [value]);

  // Emit crop string when crop changes
  useEffect(() => {
  // Disable crop emission unless a new file is being uploaded
  if (!sourceFile) return;
  if (mode === 'pad') {
      // In pad mode we include whole image; clear crop string (caller can decide)
      onChange?.(null);
      return;
    }
  if (!dims.w || !crop.size) return;
    const x1 = Math.round(crop.x);
    const y1 = Math.round(crop.y);
    const x2 = Math.round(crop.x + crop.size);
    const y2 = Math.round(crop.y + crop.size);
  const out = `${x1},${y1},${x2},${y2}`;
  if(lastEmitted.current === out) return; // avoid redundant callbacks
  lastEmitted.current = out;
  onChange?.(out);
  }, [crop, dims, mode, onChange]);

  const startDrag = (e) => {
  if (disabled || mode !== 'crop' || !sourceFile) return; // only allow dragging when new file selected
    if (!imgRef.current || !containerRef.current) return;
    e.preventDefault();
    const containerRect = containerRef.current.getBoundingClientRect();
    const imageRect = imgRef.current.getBoundingClientRect();
    // Pointer position relative to image top-left (not container!)
    const px = e.clientX - imageRect.left;
    const py = e.clientY - imageRect.top;
    // Scale from natural -> displayed
    const scale = dims.w ? (imageRect.width / dims.w) : 1;
    const cx = crop.x * scale;
    const cy = crop.y * scale;
    const csize = crop.size * scale;
    if (px >= cx && px <= cx + csize && py >= cy && py <= cy + csize) {
      dragOffset.current = { dx: px - cx, dy: py - cy, imageOffsetX: imageRect.left - containerRect.left, imageOffsetY: imageRect.top - containerRect.top };
      setDragging(true);
    }
  };
  const onDrag = (e) => {
    if (!dragging || disabled) return;
    if (!imgRef.current) return;
    const imageRect = imgRef.current.getBoundingClientRect();
    // Position relative to image
    const px = e.clientX - imageRect.left;
    const py = e.clientY - imageRect.top;
    const scale = dims.w ? (imageRect.width / dims.w) : 1;
    let nx = (px - dragOffset.current.dx) / scale;
    let ny = (py - dragOffset.current.dy) / scale;
    nx = Math.max(0, Math.min(nx, dims.w - crop.size));
    ny = Math.max(0, Math.min(ny, dims.h - crop.size));
    setCrop(c => ({ ...c, x: nx, y: ny }));
  };
  const endDrag = () => setDragging(false);

  useEffect(() => {
    window.addEventListener('mousemove', onDrag);
    window.addEventListener('mouseup', endDrag);
    return () => { window.removeEventListener('mousemove', onDrag); window.removeEventListener('mouseup', endDrag); };
  }, [onDrag]);

  const handleSizeChange = (e) => {
    const v = parseFloat(e.target.value);
    if (!dims.w) return;
    const maxSize = Math.min(dims.w, dims.h);
    const size = Math.max(10, Math.min(maxSize, v));
    // Keep centered relative to previous center
    const cx = crop.x + crop.size / 2;
    const cy = crop.y + crop.size / 2;
    let nx = cx - size / 2;
    let ny = cy - size / 2;
    nx = Math.max(0, Math.min(nx, dims.w - size));
    ny = Math.max(0, Math.min(ny, dims.h - size));
    setCrop(c => ({ ...c, x: nx, y: ny, size }));
  };

  const percentSize = () => {
    const maxSize = Math.min(dims.w, dims.h) || 1;
    return Math.round(crop.size);
  };

  // Build a preview canvas data URL for quick square preview
  const previewUrl = (() => {
    try {
      if (!imgRef.current || !dims.w) return null;
      const canvas = document.createElement('canvas');
      const squareSize = mode === 'pad' ? Math.max(dims.w, dims.h) : crop.size;
      if (!squareSize) return null;
      canvas.width = 200; canvas.height = 200;
      const ctx = canvas.getContext('2d');
      if (mode === 'pad') {
        const full = Math.max(dims.w, dims.h);
        // white background
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0,0,200,200);
        const scale = 200 / full;
        const offsetX = (full - dims.w) / 2;
        const offsetY = (full - dims.h) / 2;
        ctx.drawImage(imgRef.current, 0,0,dims.w,dims.h, offsetX*scale, offsetY*scale, dims.w*scale, dims.h*scale);
      } else {
        const scale = 200 / crop.size;
        ctx.drawImage(imgRef.current, crop.x, crop.y, crop.size, crop.size, 0, 0, 200, 200);
      }
      return canvas.toDataURL('image/png');
    } catch { return null; }
  })();

  // Export processed square image (Blob)
  const exportSquareBlob = useCallback(() => {
    if (!imgRef.current || !dims.w) return null;
    // Limit output dimensions to keep file sizes reasonable
    const MAX_OUT = 2048; // px
    const baseSquare = mode === 'pad' ? Math.max(dims.w, dims.h) : (crop.size || Math.min(dims.w, dims.h));
    if (!baseSquare) return null;
    const outSize = Math.min(baseSquare, MAX_OUT);

    const canvas = document.createElement('canvas');
    canvas.width = outSize; canvas.height = outSize;
    const ctx = canvas.getContext('2d');
    // Always paint a white background so JPEG has no transparency artifacts
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0,0,outSize,outSize);

    if (mode === 'pad') {
      // Scale entire image to fit within outSize square and center it
      const full = Math.max(dims.w, dims.h);
      const s = outSize / full;
      const drawW = Math.round(dims.w * s);
      const drawH = Math.round(dims.h * s);
      const dx = Math.round((outSize - drawW) / 2);
      const dy = Math.round((outSize - drawH) / 2);
      ctx.drawImage(imgRef.current, 0, 0, dims.w, dims.h, dx, dy, drawW, drawH);
    } else {
      // Crop to square and scale to outSize
      ctx.drawImage(
        imgRef.current,
        crop.x, crop.y, crop.size, crop.size,
        0, 0, outSize, outSize
      );
    }
    // Encode as JPEG to keep sizes small
    return new Promise(resolve => canvas.toBlob(b => resolve(b), 'image/jpeg', 0.88));
  }, [crop, dims, mode]);

  useImperativeHandle(ref, () => ({
    async getProcessedBlob() { return await exportSquareBlob(); },
    getMode() { return mode; }
  }), [exportSquareBlob, mode]);

  useEffect(()=>{ onModeChange?.(mode); try { localStorage.setItem('ppp_cover_mode', mode); } catch {} },[mode,onModeChange]);

  return (
    <div className="space-y-2">
  <div
        ref={containerRef}
        className="relative border rounded overflow-hidden max-h-72 bg-gray-50 flex items-center justify-center"
        style={{ cursor: dragging ? 'grabbing' : 'grab', userSelect: 'none' }}
        onMouseDown={startDrag}
      >
        {imgUrl ? (
          <img ref={imgRef} src={imgUrl} alt="Cover" onLoad={handleImageLoad} className="max-w-full max-h-72 select-none" draggable={false} />
        ) : (
          <div className="text-xs text-gray-500 p-4">No image selected</div>
        )}
        {imgUrl && crop.size > 0 && mode === 'crop' && (() => {
          if(!imgRef.current || !containerRef.current) return null;
          const imgRect = imgRef.current.getBoundingClientRect();
          const contRect = containerRef.current.getBoundingClientRect();
          const dw = imgRect.width || 1;
          const dh = imgRect.height || 1;
          const offsetX = imgRect.left - contRect.left;
          const offsetY = imgRect.top - contRect.top;
          const scaleX = dw / dims.w;
          const scaleY = dh / dims.h; // normally equal, but be robust
          const left = offsetX + crop.x * scaleX;
          const top = offsetY + crop.y * scaleY;
          const sizeW = crop.size * scaleX;
          const sizeH = crop.size * scaleY;
          return (
            <div
              className="absolute border-2 border-blue-500/90 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)] box-content"
              style={{ left, top, width: sizeW, height: sizeH }}
              title="Drag to move. Use slider to resize."
            />
          );
        })()}
      </div>
      {dims.w > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-[11px]">
            <button type="button" disabled={disabled || !sourceFile} onClick={()=>setMode('crop')} className={`px-2 py-1 rounded border ${mode==='crop'?'bg-blue-600 text-white border-blue-600':'bg-white'} ${!sourceFile?'opacity-40 cursor-not-allowed':''}`}>Crop</button>
            <button type="button" disabled={disabled || !sourceFile} onClick={()=>setMode('pad')} className={`px-2 py-1 rounded border ${mode==='pad'?'bg-blue-600 text-white border-blue-600':'bg-white'} ${!sourceFile?'opacity-40 cursor-not-allowed':''}`}>Pad</button>
            <span className="text-gray-500">Mode</span>
          </div>
          {mode==='crop' && sourceFile && (
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wide text-gray-500">Crop Size (pixels)</label>
              <input
                type="range"
                min={10}
                max={Math.min(dims.w, dims.h)}
                value={percentSize()}
                onChange={handleSizeChange}
                disabled={disabled}
              />
              <div className="text-[11px] text-gray-500">{Math.round(crop.size)}px square • Drag box to reposition.</div>
            </div>
          )}
          {mode==='pad' && sourceFile && (
            <div className="text-[11px] text-gray-500">Entire image will be centered on white square ({Math.max(dims.w,dims.h)}px).</div>
          )}
        </div>
      )}
      {previewUrl && (
        <div className="flex items-center gap-3 mt-2">
          <div className="text-[11px] text-gray-500">Preview:</div>
          <img src={previewUrl} alt="Crop preview" className="w-16 h-16 rounded border object-cover" />
          <div className="text-[10px] text-gray-400">Stored as {value || ''}</div>
        </div>
      )}
    </div>
  );
});

export default CoverCropper;
