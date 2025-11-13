import React, { useEffect, useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/AuthContext';
import { makeApi } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';
import { 
  Save, 
  RotateCcw, 
  AlertTriangle,
  CheckCircle,
  X,
  Loader2,
  Plus,
  Edit,
  Trash2,
  ChevronUp,
  ChevronDown,
  GripVertical
} from 'lucide-react';

export default function AdminTierEditorV2() {
  const { token } = useAuth();
  const { toast } = useToast();
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [pricingData, setPricingData] = useState(null);
  const [editedTiers, setEditedTiers] = useState({});
  const [editedFeatures, setEditedFeatures] = useState([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [editingFeature, setEditingFeature] = useState(null);
  const [showFeatureDialog, setShowFeatureDialog] = useState(false);
  const [isEditingExistingFeature, setIsEditingExistingFeature] = useState(false);

  useEffect(() => {
    fetchData();
  }, [token]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = makeApi(token);
      const response = await api.get('/api/admin/pricing');
      setPricingData(response);
      
      // Initialize edited features with current values (deep copy)
      const features = response.featureDefinitions || [];
      setEditedFeatures(features.map(f => JSON.parse(JSON.stringify(f))));
      
      // Initialize edited tiers with current values (deep copy)
      const initial = {};
      response.standardTiers.forEach(tier => {
        initial[tier.key] = JSON.parse(JSON.stringify(tier));
      });
      setEditedTiers(initial);
      setHasChanges(false);
    } catch (e) {
      const msg = e?.detail || e?.message || 'Failed to load pricing configuration';
      setError(msg);
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const updateTierValue = (tierKey, fieldPath, value) => {
    setEditedTiers(prev => {
      const updated = { ...prev };
      if (!updated[tierKey]) {
        const originalTier = pricingData.standardTiers.find(t => t.key === tierKey);
        if (originalTier) {
          updated[tierKey] = JSON.parse(JSON.stringify(originalTier));
        } else {
          return prev;
        }
      }
      
      // Handle nested field paths (e.g., "features.flubber")
      if (fieldPath.includes('.')) {
        const parts = fieldPath.split('.');
        const lastPart = parts.pop();
        let target = updated[tierKey];
        for (const part of parts) {
          if (!target[part]) target[part] = {};
          target = target[part];
        }
        target[lastPart] = value;
        // Create new object to trigger re-render
        updated[tierKey] = { ...updated[tierKey] };
      } else {
        updated[tierKey] = {
          ...updated[tierKey],
          [fieldPath]: value
        };
      }
      
      return updated;
    });
    
    setHasChanges(true);
  };

  const getTierValue = (tierKey, fieldPath) => {
    const tier = editedTiers[tierKey] || pricingData?.standardTiers.find(t => t.key === tierKey);
    if (!tier) return null;
    
    // Handle nested field paths
    if (fieldPath.includes('.')) {
      const parts = fieldPath.split('.');
      let value = tier;
      for (const part of parts) {
        if (value == null) return null;
        value = value[part];
      }
      return value ?? null;
    }
    
    return tier[fieldPath] ?? null;
  };

  const saveAll = async () => {
    setSaving(true);
    try {
      const api = makeApi(token);
      
      // Build updated tiers
      const updatedTiers = pricingData.standardTiers.map(tier => {
        const edited = editedTiers[tier.key];
        if (!edited) return tier;
        
        return {
          ...tier,
          ...edited,
          features: {
            ...tier.features,
            ...(edited.features || {})
          }
        };
      });
      
      // Sort features by order before saving
      const sortedFeatures = [...editedFeatures].sort((a, b) => a.order - b.order);
      
      const updatedData = {
        standardTiers: updatedTiers,
        earlyAccessTiers: pricingData.earlyAccessTiers || null,
        featureDefinitions: sortedFeatures
      };
      
      await api.put('/api/admin/pricing', updatedData);
      
      toast({ 
        title: 'Success', 
        description: 'Pricing configuration updated successfully. Changes will be reflected on the pricing page.' 
      });
      
      setHasChanges(false);
      await fetchData();
    } catch (e) {
      const msg = e?.detail?.message || e?.detail || e?.message || 'Failed to save pricing configuration';
      toast({ title: 'Save Failed', description: msg, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const resetChanges = () => {
    if (!pricingData) return;
    const initial = {};
    pricingData.standardTiers.forEach(tier => {
      initial[tier.key] = JSON.parse(JSON.stringify(tier));
    });
    setEditedTiers(initial);
    const features = pricingData.featureDefinitions || [];
    setEditedFeatures(features.map(f => JSON.parse(JSON.stringify(f))));
    setHasChanges(false);
  };

  const openNewFeatureDialog = () => {
    setIsEditingExistingFeature(false);
    // Calculate next order: max order + 1, or length + 1 if no features
    const nextOrder = editedFeatures.length > 0 
      ? Math.max(...editedFeatures.map(f => f.order || 0)) + 1 
      : 1;
    setEditingFeature({
      key: '',
      label: '',
      description: '',
      type: 'text',
      options: null,
      fieldPath: '',
      order: nextOrder,
      category: 'general'
    });
    setShowFeatureDialog(true);
  };

  const openEditFeatureDialog = (feature) => {
    setIsEditingExistingFeature(true);
    setEditingFeature(JSON.parse(JSON.stringify(feature)));
    setShowFeatureDialog(true);
  };

  const saveFeature = () => {
    if (!editingFeature) return;
    
    if (!editingFeature.key || !editingFeature.label || !editingFeature.fieldPath) {
      toast({ title: 'Error', description: 'Key, label, and field path are required', variant: 'destructive' });
      return;
    }
    
    if (isEditingExistingFeature) {
      // Update existing feature - find by original key
      const originalKey = editingFeature.key; // Key shouldn't change for existing features
      const existingIndex = editedFeatures.findIndex(f => f.key === originalKey);
      if (existingIndex >= 0) {
        const updated = [...editedFeatures];
        updated[existingIndex] = editingFeature;
        setEditedFeatures(updated);
      }
    } else {
      // Check if key already exists (for new features)
      if (editedFeatures.some(f => f.key === editingFeature.key)) {
        toast({ title: 'Error', description: 'A feature with this key already exists', variant: 'destructive' });
        return;
      }
      // Add new feature
      setEditedFeatures([...editedFeatures, editingFeature]);
    }
    
    setShowFeatureDialog(false);
    setEditingFeature(null);
    setIsEditingExistingFeature(false);
    setHasChanges(true);
  };

  const deleteFeature = (featureKey) => {
    if (!confirm(`Are you sure you want to delete the feature "${featureKey}"?`)) {
      return;
    }
    setEditedFeatures(editedFeatures.filter(f => f.key !== featureKey));
    setHasChanges(true);
  };

  const moveFeature = (sortedIndex, direction) => {
    if (direction === 'up' && sortedIndex === 0) return;
    if (direction === 'down' && sortedIndex === sortedFeatures.length - 1) return;
    
    // Get the feature to move and its target neighbor from sorted array
    const featureToMove = sortedFeatures[sortedIndex];
    const targetIndex = direction === 'up' ? sortedIndex - 1 : sortedIndex + 1;
    const targetFeature = sortedFeatures[targetIndex];
    
    if (!featureToMove || !targetFeature) return;
    
    // Find indices in editedFeatures array
    const moveIndex = editedFeatures.findIndex(f => f.key === featureToMove.key);
    const targetIdx = editedFeatures.findIndex(f => f.key === targetFeature.key);
    
    if (moveIndex === -1 || targetIdx === -1) return;
    
    // Swap order values by creating new objects
    const updated = editedFeatures.map((f, i) => {
      if (i === moveIndex) {
        return { ...f, order: targetFeature.order };
      } else if (i === targetIdx) {
        return { ...f, order: featureToMove.order };
      }
      return f;
    });
    
    setEditedFeatures(updated);
    setHasChanges(true);
  };

  const renderCell = (feature, tier) => {
    const value = getTierValue(tier.key, feature.fieldPath);
    
    if (feature.type === 'boolean') {
      const isChecked = !!value;
      return (
        <TableCell 
          className="text-center p-2"
        >
          <button
            type="button"
            onClick={() => updateTierValue(tier.key, feature.fieldPath, !isChecked)}
            className="w-full h-8 flex items-center justify-center hover:bg-gray-100 rounded transition-colors"
            title={`Click to ${isChecked ? 'disable' : 'enable'}`}
          >
            {isChecked ? (
              <CheckCircle className="h-6 w-6 text-green-600" />
            ) : (
              <X className="h-6 w-6 text-red-500" />
            )}
          </button>
        </TableCell>
      );
    }
    
    if (feature.type === 'number') {
      return (
        <TableCell className="p-2 text-center">
          <Input
            type="number"
            className="w-full max-w-[100px] text-center h-8 mx-auto"
            value={value === null || value === undefined ? '' : value}
            placeholder="—"
            onChange={(e) => {
              const val = e.target.value;
              if (val === '') {
                updateTierValue(tier.key, feature.fieldPath, null);
              } else {
                const num = Number(val);
                updateTierValue(tier.key, feature.fieldPath, isNaN(num) ? 0 : num);
              }
            }}
          />
        </TableCell>
      );
    }
    
    if (feature.type === 'select') {
      return (
        <TableCell className="p-2 text-center">
          <div className="flex justify-center">
            <Select
              value={value || (feature.options && feature.options[0]) || ''}
              onValueChange={(val) => updateTierValue(tier.key, feature.fieldPath, val)}
            >
              <SelectTrigger className="w-full max-w-[120px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {feature.options?.map(option => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </TableCell>
      );
    }
    
    // Default: text input
    return (
      <TableCell className="p-2 text-center">
        <Input
          type="text"
          className="w-full max-w-[120px] text-center h-8 text-sm mx-auto"
          value={value === null || value === undefined ? '' : String(value)}
          placeholder="—"
          onChange={(e) => {
            let val = e.target.value;
            // Handle boolean strings for multiUser or similar fields
            if (feature.fieldPath === 'features.multiUser') {
              if (val.toLowerCase() === 'true') val = true;
              else if (val.toLowerCase() === 'false') val = false;
            }
            updateTierValue(tier.key, feature.fieldPath, val);
          }}
        />
      </TableCell>
    );
  };

  // Sort features by order
  const sortedFeatures = useMemo(() => {
    return [...editedFeatures].sort((a, b) => a.order - b.order);
  }, [editedFeatures]);

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin mr-3" />
            <span>Loading pricing configuration...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <Button onClick={fetchData} className="mt-4">
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!pricingData) return null;

  const tiers = pricingData.standardTiers || [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Tier Editor</CardTitle>
              <CardDescription>
                Edit subscription plan features and benefits. Click checkmarks/X to toggle, or edit values directly in cells.
                Changes are saved to the pricing page.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={openNewFeatureDialog}
                disabled={saving}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add Benefit
              </Button>
              <Button
                variant="outline"
                onClick={resetChanges}
                disabled={saving || !hasChanges}
              >
                <RotateCcw className="h-4 w-4 mr-2" />
                Reset
              </Button>
              <Button
                onClick={saveAll}
                disabled={saving || !hasChanges}
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save All Changes
                  </>
                )}
              </Button>
            </div>
          </div>
          {hasChanges && (
            <Alert className="mt-2">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                You have unsaved changes. Click "Save All Changes" to update the pricing page.
              </AlertDescription>
            </Alert>
          )}
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50">
                  <TableHead className="font-bold sticky left-0 bg-gray-50 z-10 min-w-[300px] max-w-[300px] border-r shadow-sm">
                    <div className="py-2">Benefit / Feature</div>
                  </TableHead>
                  {tiers.map(tier => (
                    <TableHead key={tier.key} className="text-center font-bold min-w-[160px] bg-gray-50">
                      <div className="flex flex-col items-center gap-1 py-2">
                        <span className="text-base">{tier.name}</span>
                        {tier.popular && (
                          <Badge variant="secondary" className="text-xs">{tier.badge || 'Popular'}</Badge>
                        )}
                      </div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedFeatures.map((feature, index) => (
                  <TableRow key={feature.key} className="hover:bg-gray-50/50 border-b group">
                    <TableCell className="font-medium sticky left-0 bg-white z-10 border-r shadow-sm min-w-[300px] max-w-[300px]">
                      <div className="flex items-center gap-2 py-2">
                        <div className="flex flex-col gap-1 flex-1">
                          <div className="flex items-center gap-2">
                            <GripVertical className="h-4 w-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                            <div className="font-semibold text-sm text-gray-900">{feature.label}</div>
                            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 w-6 p-0"
                                onClick={() => openEditFeatureDialog(feature)}
                                title="Edit feature"
                              >
                                <Edit className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-6 w-6 p-0 text-red-600 hover:text-red-700"
                                onClick={() => deleteFeature(feature.key)}
                                title="Delete feature"
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                          {feature.description && (
                            <div className="text-xs text-gray-500 mt-1 leading-relaxed ml-6">
                              {feature.description}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => moveFeature(index, 'up')}
                            disabled={index === 0}
                            title="Move up"
                          >
                            <ChevronUp className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            onClick={() => moveFeature(index, 'down')}
                            disabled={index === sortedFeatures.length - 1}
                            title="Move down"
                          >
                            <ChevronDown className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </TableCell>
                    {tiers.map(tier => renderCell(feature, tier))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Feature Edit Dialog */}
      <Dialog open={showFeatureDialog} onOpenChange={setShowFeatureDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingFeature?.key ? 'Edit Benefit' : 'New Benefit'}</DialogTitle>
            <DialogDescription>
              Define a benefit or feature that will appear as a row in the pricing matrix.
            </DialogDescription>
          </DialogHeader>
          {editingFeature && (
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="key">Key (unique identifier)</Label>
                  <Input
                    id="key"
                    value={editingFeature.key}
                    onChange={(e) => setEditingFeature({...editingFeature, key: e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '')})}
                    placeholder="e.g., credits"
                    disabled={isEditingExistingFeature}
                  />
                  <p className="text-xs text-gray-500">
                    {isEditingExistingFeature 
                      ? 'Key cannot be changed for existing features' 
                      : 'Unique identifier (lowercase, alphanumeric only)'}
                  </p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="label">Label (display name)</Label>
                  <Input
                    id="label"
                    value={editingFeature.label}
                    onChange={(e) => setEditingFeature({...editingFeature, label: e.target.value})}
                    placeholder="e.g., Monthly Credits"
                  />
                  <p className="text-xs text-gray-500">Displayed in the pricing table</p>
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="description">Description</Label>
                <Input
                  id="description"
                  value={editingFeature.description}
                  onChange={(e) => setEditingFeature({...editingFeature, description: e.target.value})}
                  placeholder="Optional description/tooltip"
                />
                <p className="text-xs text-gray-500">Shown as tooltip in the editor</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="type">Type</Label>
                  <Select
                    value={editingFeature.type}
                    onValueChange={(val) => setEditingFeature({...editingFeature, type: val, options: val === 'select' ? ['Option 1'] : null})}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="boolean">Boolean (Checkmark/X)</SelectItem>
                      <SelectItem value="number">Number</SelectItem>
                      <SelectItem value="text">Text</SelectItem>
                      <SelectItem value="select">Select (Dropdown)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="fieldPath">Field Path *</Label>
                  <Input
                    id="fieldPath"
                    value={editingFeature.fieldPath}
                    onChange={(e) => setEditingFeature({...editingFeature, fieldPath: e.target.value})}
                    placeholder="e.g., credits or features.flubber"
                  />
                  <p className="text-xs text-gray-500">Where to store the value. Use "features.X" for feature flags.</p>
                </div>
              </div>
              {editingFeature.type === 'select' && (
                <div className="grid gap-2">
                  <Label htmlFor="options">Options (comma-separated)</Label>
                  <Input
                    id="options"
                    value={editingFeature.options?.join(', ') || ''}
                    onChange={(e) => {
                      const options = e.target.value.split(',').map(s => s.trim()).filter(s => s);
                      setEditingFeature({...editingFeature, options: options.length > 0 ? options : null});
                    }}
                    placeholder="e.g., Low, Medium, High, Highest"
                  />
                  <p className="text-xs text-gray-500">Comma-separated list of options for the dropdown</p>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowFeatureDialog(false)}>
              Cancel
            </Button>
            <Button onClick={saveFeature}>
              {isEditingExistingFeature ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
