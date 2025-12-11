import React, { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2, Edit, AlertCircle, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export default function AffiliateSettingsTab({ token }) {
    const { toast } = useToast();
    const [loading, setLoading] = useState(true);
    const [settings, setSettings] = useState([]);
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [editingSetting, setEditingSetting] = useState(null);
    const [saving, setSaving] = useState(false);

    // Form state
    const [formData, setFormData] = useState({
        user_id: "",
        referrer_reward_credits: "20.0",
        referee_discount_percent: "20",
        referee_discount_duration: "once",
        is_active: true
    });

    const fetchSettings = async () => {
        setLoading(true);
        try {
            const response = await fetch("/api/admin/affiliate-settings/", {
                headers: { Authorization: `Bearer ${token}` }
            });
            if (!response.ok) throw new Error("Failed to fetch settings");
            const data = await response.json();
            setSettings(data);
        } catch (error) {
            toast({
                title: "Error",
                description: error.message,
                variant: "destructive"
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSettings();
    }, [token]);

    const handleOpenDialog = (setting = null) => {
        if (setting) {
            setEditingSetting(setting);
            setFormData({
                user_id: setting.user_id || "",
                referrer_reward_credits: setting.referrer_reward_credits.toString(),
                referee_discount_percent: setting.referee_discount_percent.toString(),
                referee_discount_duration: setting.referee_discount_duration,
                is_active: setting.is_active
            });
        } else {
            setEditingSetting(null);
            setFormData({
                user_id: "",
                referrer_reward_credits: "20.0",
                referee_discount_percent: "20",
                referee_discount_duration: "once",
                is_active: true
            });
        }
        setIsDialogOpen(true);
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const payload = {
                referrer_reward_credits: parseFloat(formData.referrer_reward_credits),
                referee_discount_percent: parseInt(formData.referee_discount_percent),
                referee_discount_duration: formData.referee_discount_duration,
                is_active: formData.is_active,
                user_id: formData.user_id ? formData.user_id : null
            };

            const response = await fetch("/api/admin/affiliate-settings/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Failed to save settings");

            toast({
                title: "Success",
                description: "Affiliate settings saved successfully"
            });
            setIsDialogOpen(false);
            fetchSettings();
        } catch (error) {
            toast({
                title: "Error",
                description: error.message,
                variant: "destructive"
            });
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm("Are you sure you want to delete this setting override?")) return;

        try {
            const response = await fetch(`/api/admin/affiliate-settings/${id}`, {
                method: "DELETE",
                headers: { Authorization: `Bearer ${token}` }
            });

            if (!response.ok) throw new Error("Failed to delete setting");

            toast({ title: "Deleted", description: "Override removed" });
            fetchSettings();
        } catch (error) {
            toast({ title: "Error", description: error.message, variant: "destructive" });
        }
    };

    const defaultSetting = settings.find(s => s.user_id === null);
    const userOverrides = settings.filter(s => s.user_id !== null);

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Referral Settings</h2>
                    <p className="text-muted-foreground">Manage global defaults and user-specific negotiated deals.</p>
                </div>
                <Button onClick={() => handleOpenDialog()}>
                    <Plus className="mr-2 h-4 w-4" /> Add Override
                </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-1">
                <Card>
                    <CardHeader>
                        <CardTitle>Global Default</CardTitle>
                        <CardDescription>Applied to all users unless an override exists.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {loading ? (
                            <div className="flex items-center justify-center p-4"><Loader2 className="animate-spin h-6 w-6" /></div>
                        ) : defaultSetting ? (
                            <div className="flex items-center justify-between bg-muted/50 p-4 rounded-lg border">
                                <div className="space-y-1">
                                    <div className="font-semibold">Give {defaultSetting.referee_discount_percent}% Off ({defaultSetting.referee_discount_duration})</div>
                                    <div className="text-sm text-muted-foreground">Get {defaultSetting.referrer_reward_credits} Credits</div>
                                </div>
                                <Button variant="outline" size="sm" onClick={() => handleOpenDialog(defaultSetting)}>
                                    <Edit className="mr-2 h-4 w-4" /> Edit Default
                                </Button>
                            </div>
                        ) : (
                            <div className="flex items-center justify-between bg-yellow-50 p-4 rounded-lg border border-yellow-200">
                                <div className="flex items-center text-yellow-800">
                                    <AlertCircle className="mr-2 h-5 w-5" /> No global default set. Referral system is effectively disabled.
                                </div>
                                <Button size="sm" onClick={() => handleOpenDialog(null)}>
                                    Create Default
                                </Button>
                            </div>
                        )}
                    </CardContent>
                </Card>

                {userOverrides.length > 0 && (
                    <Card>
                        <CardHeader>
                            <CardTitle>User Overrides</CardTitle>
                            <CardDescription>Special deals negotiated for specific influencers/partners.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>User ID</TableHead>
                                        <TableHead>Give (Discount)</TableHead>
                                        <TableHead>Get (Reward)</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead className="text-right">Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {userOverrides.map((setting) => (
                                        <TableRow key={setting.id}>
                                            <TableCell className="font-mono text-xs">{setting.user_id}</TableCell>
                                            <TableCell>{setting.referee_discount_percent}% ({setting.referee_discount_duration})</TableCell>
                                            <TableCell>{setting.referrer_reward_credits} Credits</TableCell>
                                            <TableCell>
                                                <Badge variant={setting.is_active ? "default" : "secondary"}>
                                                    {setting.is_active ? "Active" : "Inactive"}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-right">
                                                <Button variant="ghost" size="icon" onClick={() => handleOpenDialog(setting)}>
                                                    <Edit className="h-4 w-4" />
                                                </Button>
                                                <Button variant="ghost" size="icon" className="text-red-500 hover:text-red-600" onClick={() => handleDelete(setting.id)}>
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                )}
            </div>

            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{editingSetting ? "Edit Setting" : "Create Setting"}</DialogTitle>
                        <DialogDescription>
                            Configure the "Give/Get" rewards.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid gap-4 py-4">
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="user_id" className="text-right">
                                User ID
                            </Label>
                            <Input
                                id="user_id"
                                placeholder="Empty for Global Default"
                                value={formData.user_id}
                                onChange={(e) => setFormData({ ...formData, user_id: e.target.value })}
                                className="col-span-3 font-mono text-sm"
                            />
                        </div>
                        <p className="text-[0.8rem] text-muted-foreground text-right pl-24">
                            Leave empty to set the Global Default. Enter a UUID to override for that user.
                        </p>

                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="discount" className="text-right">
                                Referee Discount (%)
                            </Label>
                            <Input
                                id="discount"
                                type="number"
                                value={formData.referee_discount_percent}
                                onChange={(e) => setFormData({ ...formData, referee_discount_percent: e.target.value })}
                                className="col-span-3"
                            />
                        </div>

                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="duration" className="text-right">
                                Discount Duration
                            </Label>
                            <Select
                                value={formData.referee_discount_duration}
                                onValueChange={(val) => setFormData({ ...formData, referee_discount_duration: val })}
                            >
                                <SelectTrigger className="col-span-3">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="once">Once (One-time)</SelectItem>
                                    <SelectItem value="repeating">Repeating (Multi-month)</SelectItem>
                                    <SelectItem value="forever">Forever (Recurring)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="reward" className="text-right">
                                Referrer Reward
                            </Label>
                            <Input
                                id="reward"
                                type="number"
                                value={formData.referrer_reward_credits}
                                onChange={(e) => setFormData({ ...formData, referrer_reward_credits: e.target.value })}
                                className="col-span-3"
                            />
                            <span className="col-start-2 col-span-3 text-xs text-muted-foreground">Credits for the referrer</span>
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setIsDialogOpen(false)}>Cancel</Button>
                        <Button onClick={handleSave} disabled={saving}>
                            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Save Changes
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
