import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useAuth } from '@/AuthContext';
import { makeApi } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';
import { 
  Info, 
  AlertTriangle, 
  CheckCircle, 
  Save, 
  RotateCcw, 
  Clock,
  CreditCard,
  Zap,
  Sparkles,
  Settings,
  TrendingUp,
  Shield,
  DollarSign,
  Table as TableIcon
} from 'lucide-react';

const CATEGORY_CONFIG = {
  credits: { label: 'Credits & Quotas', icon: CreditCard, color: 'text-blue-600' },
  processing: { label: 'Audio Processing', icon: Settings, color: 'text-purple-600' },
  ai_tts: { label: 'AI & TTS', icon: Sparkles, color: 'text-pink-600' },
  editing: { label: 'Editing Features', icon: Zap, color: 'text-green-600' },
  branding: { label: 'Branding & Publishing', icon: TrendingUp, color: 'text-orange-600' },
  analytics: { label: 'Analytics & Insights', icon: TrendingUp, color: 'text-indigo-600' },
  support: { label: 'Support & Priority', icon: Shield, color: 'text-gray-600' },
  costs: { label: 'Cost Multipliers', icon: DollarSign, color: 'text-red-600' },
};

export default function AdminTierEditorV2() {
  const { token } = useAuth();
  const { toast } = useToast();
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [editedFeatures, setEditedFeatures] = useState({});
  const [selectedTier, setSelectedTier] = useState('free');
  const [activeCategory, setActiveCategory] = useState('credits');
  const [validationErrors, setValidationErrors] = useState([]);
  const [showHardCodedComparison, setShowHardCodedComparison] = useState(false);
  const [viewMode, setViewMode] = useState('edit'); // 'edit' or 'comparison'

  useEffect(() => {
    fetchData();
  }, [token]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const api = makeApi(token);
      const response = await api.get('/api/admin/tiers/v2');
      setData(response);
      
      // Initialize edited features with current values
      const initial = {};
      response.tiers.forEach(tier => {
        initial[tier.tier_name] = {};
        response.features.forEach(feature => {
          initial[tier.tier_name][feature.key] = feature.values[tier.tier_name];
        });
      });
      setEditedFeatures(initial);
    } catch (e) {
      const msg = e?.detail || e?.message || 'Failed to load tier configuration';
      setError(msg);
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const updateFeatureValue = (tierName, featureKey, value) => {
    setEditedFeatures(prev => ({
      ...prev,
      [tierName]: {
        ...prev[tierName],
        [featureKey]: value
      }
    }));
    
    // Clear validation errors when user makes changes
    setValidationErrors([]);
  };

  const validateTierConfig = (tierName) => {
    const features = editedFeatures[tierName];
    const errors = [];

    // Validate Auphonic dependencies
    if (features.auto_filler_removal && features.audio_pipeline !== 'auphonic') {
      errors.push('Auto filler removal requires Auphonic pipeline');
    }
    if (features.auto_noise_reduction && features.audio_pipeline !== 'auphonic') {
      errors.push('Auto noise reduction requires Auphonic pipeline');
    }
    if (features.auto_leveling && features.audio_pipeline !== 'auphonic') {
      errors.push('Auto leveling requires Auphonic pipeline');
    }

    // Validate ElevenLabs dependencies
    if (features.elevenlabs_voices > 0 && features.tts_provider !== 'elevenlabs') {
      errors.push('ElevenLabs voice clones require ElevenLabs TTS provider');
    }

    // Validate negative values
    Object.entries(features).forEach(([key, value]) => {
      if (typeof value === 'number' && value < 0) {
        errors.push(`${key} cannot be negative`);
      }
    });

    // Validate multipliers
    if (features.auphonic_cost_multiplier && features.auphonic_cost_multiplier < 1.0) {
      errors.push('Auphonic cost multiplier must be >= 1.0');
    }
    if (features.elevenlabs_cost_multiplier && features.elevenlabs_cost_multiplier < 1.0) {
      errors.push('ElevenLabs cost multiplier must be >= 1.0');
    }

    return errors;
  };

  const saveTier = async (tierName) => {
    const errors = validateTierConfig(tierName);
    if (errors.length > 0) {
      setValidationErrors(errors);
      toast({ 
        title: 'Validation Failed', 
        description: errors[0], 
        variant: 'destructive' 
      });
      return;
    }

    setSaving(true);
    try {
      const api = makeApi(token);
      await api.put('/api/admin/tiers/v2', {
        tier_name: tierName,
        features: editedFeatures[tierName],
        reason: 'Updated via admin tier editor'
      });
      
      toast({ 
        title: 'Success', 
        description: `${tierName.charAt(0).toUpperCase() + tierName.slice(1)} tier updated successfully` 
      });
      
      // Refresh data
      await fetchData();
    } catch (e) {
      const msg = e?.detail?.message || e?.detail || e?.message || 'Failed to save tier configuration';
      toast({ title: 'Save Failed', description: msg, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const resetTier = (tierName) => {
    if (!data) return;
    const reset = {};
    data.features.forEach(feature => {
      reset[feature.key] = feature.values[tierName];
    });
    setEditedFeatures(prev => ({
      ...prev,
      [tierName]: reset
    }));
    setValidationErrors([]);
  };

  const featuresByCategory = useMemo(() => {
    if (!data) return {};
    
    const grouped = {};
    data.features.forEach(feature => {
      const category = feature.category || 'other';
      if (!grouped[category]) {
        grouped[category] = [];
      }
      grouped[category].push(feature);
    });
    return grouped;
  }, [data]);

  const calculateCreditsFromMinutes = (minutes) => {
    if (minutes === null || minutes === undefined) return 'Unlimited';
    return (minutes * 1.5).toFixed(0);
  };

  const renderFeatureControl = (feature, tierName) => {
    const value = editedFeatures[tierName]?.[feature.key];
    
    if (feature.type === 'boolean') {
      return (
        <div className="flex justify-center">
          <Switch
            checked={!!value}
            onCheckedChange={(checked) => updateFeatureValue(tierName, feature.key, checked)}
          />
        </div>
      );
    }
    
    if (feature.type === 'number') {
      return (
        <div className="flex justify-center">
          <Input
            type="number"
            className="w-32 text-center"
            value={value === null ? '' : (value ?? '')}
            placeholder="Unlimited"
            onChange={(e) => {
              const val = e.target.value;
              if (val === '') {
                updateFeatureValue(tierName, feature.key, null);
              } else {
                const num = Number(val);
                updateFeatureValue(tierName, feature.key, isNaN(num) ? 0 : num);
              }
            }}
          />
        </div>
      );
    }
    
    if (feature.type === 'select') {
      return (
        <div className="flex justify-center">
          <Select
            value={value || feature.options[0]}
            onValueChange={(val) => updateFeatureValue(tierName, feature.key, val)}
          >
            <SelectTrigger className="w-40">
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
      );
    }
    
    return <span className="text-sm text-gray-500">Unknown type</span>;
  };

  const renderHardCodedComparison = () => {
    if (!data || !showHardCodedComparison) return null;

    return (
      <Alert className="mb-4">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <div className="font-semibold mb-2">Hard-Coded vs Database Values</div>
          {data.tiers.map(tier => {
            const hardCoded = data.hard_coded_values[tier.tier_name];
            const dbValues = editedFeatures[tier.tier_name];
            const differences = [];
            
            Object.entries(hardCoded).forEach(([key, value]) => {
              if (JSON.stringify(dbValues[key]) !== JSON.stringify(value)) {
                differences.push(`${key}: DB=${JSON.stringify(dbValues[key])} vs Hard-coded=${JSON.stringify(value)}`);
              }
            });
            
            if (differences.length > 0) {
              return (
                <div key={tier.tier_name} className="mt-2">
                  <div className="font-medium text-sm">{tier.display_name}:</div>
                  <ul className="text-xs ml-4 mt-1 space-y-1">
                    {differences.map((diff, idx) => (
                      <li key={idx} className="text-orange-600">⚠️ {diff}</li>
                    ))}
                  </ul>
                </div>
              );
            }
            return null;
          })}
        </AlertDescription>
      </Alert>
    );
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mr-3"></div>
            <span>Loading tier configuration...</span>
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

  if (!data) return null;

  const CategoryIcon = CATEGORY_CONFIG[activeCategory]?.icon || Info;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Tier Editor v2 (Credits System)
          </CardTitle>
          <CardDescription>
            Configure features and credits for each subscription tier. Changes take effect immediately after saving.
            <div className="mt-2 flex items-center gap-2">
              <Badge variant="outline">1 minute = 1 credit</Badge>
              <Badge variant="outline">Database-driven feature gating</Badge>
            </div>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex justify-between items-center mb-4">
            <div className="flex gap-2">
              <Button
                variant={viewMode === 'edit' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('edit')}
              >
                <Settings className="h-4 w-4 mr-2" />
                Edit Mode
              </Button>
              <Button
                variant={viewMode === 'comparison' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('comparison')}
              >
                <TableIcon className="h-4 w-4 mr-2" />
                Comparison Matrix
              </Button>
              <Button
                variant={showHardCodedComparison ? 'default' : 'outline'}
                size="sm"
                onClick={() => setShowHardCodedComparison(!showHardCodedComparison)}
              >
                <Info className="h-4 w-4 mr-2" />
                {showHardCodedComparison ? 'Hide' : 'Show'} Hard-Coded Comparison
              </Button>
            </div>
          </div>

          {renderHardCodedComparison()}

          {validationErrors.length > 0 && (
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                <div className="font-semibold">Validation Errors:</div>
                <ul className="mt-2 ml-4 space-y-1">
                  {validationErrors.map((err, idx) => (
                    <li key={idx} className="text-sm">• {err}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* COMPARISON MATRIX VIEW */}
          {viewMode === 'comparison' && (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-bold sticky left-0 bg-white z-10 min-w-[200px]">Feature</TableHead>
                    {data.tiers.map(tier => (
                      <TableHead key={tier.tier_name} className="text-center font-bold min-w-[120px]">
                        {tier.display_name}
                        {!tier.is_public && <div className="text-xs text-gray-500">(Admin)</div>}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(CATEGORY_CONFIG).map(([category, config]) => {
                    const Icon = config.icon;
                    const features = featuresByCategory[category] || [];
                    if (features.length === 0) return null;
                    
                    return (
                      <React.Fragment key={category}>
                        {/* Category Header Row */}
                        <TableRow className="bg-gray-50">
                          <TableCell colSpan={data.tiers.length + 1} className="font-bold">
                            <div className="flex items-center gap-2">
                              <Icon className={`h-4 w-4 ${config.color}`} />
                              {config.label}
                            </div>
                          </TableCell>
                        </TableRow>
                        {/* Feature Rows */}
                        {features.map(feature => (
                          <TableRow key={feature.key} className="hover:bg-gray-50">
                            <TableCell className="sticky left-0 bg-white z-10">
                              <div>
                                <div className="font-medium text-sm">{feature.label}</div>
                                {feature.description && (
                                  <div className="text-xs text-gray-500 mt-1">{feature.description}</div>
                                )}
                              </div>
                            </TableCell>
                            {data.tiers.map(tier => {
                              const value = editedFeatures[tier.tier_name]?.[feature.key];
                              let displayValue;
                              
                              if (feature.type === 'boolean') {
                                displayValue = value ? (
                                  <CheckCircle className="h-5 w-5 text-green-600 mx-auto" />
                                ) : (
                                  <span className="text-gray-400 text-sm">—</span>
                                );
                              } else if (feature.type === 'number') {
                                displayValue = value === null ? (
                                  <Badge variant="secondary" className="text-xs">Unlimited</Badge>
                                ) : (
                                  <span className="font-medium">{value}</span>
                                );
                              } else if (feature.type === 'select') {
                                displayValue = (
                                  <Badge variant="outline" className="text-xs">{value}</Badge>
                                );
                              } else {
                                displayValue = <span className="text-sm">{String(value)}</span>;
                              }
                              
                              return (
                                <TableCell key={tier.tier_name} className="text-center">
                                  {displayValue}
                                </TableCell>
                              );
                            })}
                          </TableRow>
                        ))}
                      </React.Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          {/* EDIT MODE VIEW */}
          {viewMode === 'edit' && (
            <Tabs value={selectedTier} onValueChange={setSelectedTier} className="space-y-4">
            <TabsList className="grid w-full grid-cols-4">
              {data.tiers.map(tier => (
                <TabsTrigger key={tier.tier_name} value={tier.tier_name} className="capitalize">
                  {tier.display_name}
                  {!tier.is_public && <Badge variant="secondary" className="ml-2 text-xs">Admin</Badge>}
                </TabsTrigger>
              ))}
            </TabsList>

            {data.tiers.map(tier => (
              <TabsContent key={tier.tier_name} value={tier.tier_name} className="space-y-4">
                <div className="flex justify-between items-center p-4 bg-gray-50 rounded-lg">
                  <div>
                    <h3 className="text-lg font-semibold">{tier.display_name} Tier</h3>
                    <p className="text-sm text-gray-600">
                      Configure features and limits for this tier
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => resetTier(tier.tier_name)}
                      disabled={saving}
                    >
                      <RotateCcw className="h-4 w-4 mr-2" />
                      Reset
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => saveTier(tier.tier_name)}
                      disabled={saving}
                    >
                      {saving ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                          Saving...
                        </>
                      ) : (
                        <>
                          <Save className="h-4 w-4 mr-2" />
                          Save {tier.display_name}
                        </>
                      )}
                    </Button>
                  </div>
                </div>

                <Tabs value={activeCategory} onValueChange={setActiveCategory}>
                  <TabsList className="grid w-full grid-cols-4 lg:grid-cols-8">
                    {Object.entries(CATEGORY_CONFIG).map(([key, config]) => {
                      const Icon = config.icon;
                      return (
                        <TabsTrigger key={key} value={key} className="text-xs">
                          <Icon className={`h-3 w-3 mr-1 ${config.color}`} />
                          <span className="hidden lg:inline">{config.label}</span>
                        </TabsTrigger>
                      );
                    })}
                  </TabsList>

                  {Object.entries(CATEGORY_CONFIG).map(([categoryKey, categoryConfig]) => (
                    <TabsContent key={categoryKey} value={categoryKey} className="mt-4">
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2 text-lg">
                            <CategoryIcon className={`h-5 w-5 ${categoryConfig.color}`} />
                            {categoryConfig.label}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-1/3">Feature</TableHead>
                                <TableHead className="w-1/2">Description</TableHead>
                                <TableHead className="w-1/6 text-center">Value</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {featuresByCategory[categoryKey]?.map(feature => (
                                <TableRow key={feature.key}>
                                  <TableCell>
                                    <div className="font-medium">{feature.label}</div>
                                    <div className="text-xs text-gray-500 mt-1">
                                      {feature.type === 'boolean' && '✓ On/Off'}
                                      {feature.type === 'number' && '# Number'}
                                      {feature.type === 'select' && '▼ Dropdown'}
                                    </div>
                                  </TableCell>
                                  <TableCell>
                                    <div className="text-sm text-gray-700">{feature.description}</div>
                                    {feature.help_text && (
                                      <div className="text-xs text-gray-500 mt-1 italic">
                                        💡 {feature.help_text}
                                      </div>
                                    )}
                                  </TableCell>
                                  <TableCell>
                                    {renderFeatureControl(feature, tier.tier_name)}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>
                    </TabsContent>
                  ))}
                </Tabs>
              </TabsContent>
            ))}
          </Tabs>
          )}
        </CardContent>
      </Card>

      {/* Credit Calculator */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CreditCard className="h-5 w-5" />
            Credit Calculator
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {data.tiers.map(tier => {
              const credits = editedFeatures[tier.tier_name]?.monthly_credits;
              const episodes = editedFeatures[tier.tier_name]?.max_episodes_month;
              const pipeline = editedFeatures[tier.tier_name]?.audio_pipeline;
              const tts = editedFeatures[tier.tier_name]?.tts_provider;
              
              return (
                <div key={tier.tier_name} className="p-4 border rounded-lg">
                  <div className="font-semibold mb-2">{tier.display_name}</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Credits:</span>
                      <span className="font-medium">
                        {credits === null ? 'Unlimited' : credits.toLocaleString()}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Minutes:</span>
                      <span className="font-medium">
                        {credits === null ? 'Unlimited' : Math.floor(credits / 1.0).toLocaleString()}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600">Episodes:</span>
                      <span className="font-medium">
                        {episodes === null ? 'Unlimited' : episodes}
                      </span>
                    </div>
                    <div className="pt-2 border-t">
                      <div className="text-xs text-gray-500">Pipeline: {pipeline}</div>
                      <div className="text-xs text-gray-500">TTS: {tts}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
