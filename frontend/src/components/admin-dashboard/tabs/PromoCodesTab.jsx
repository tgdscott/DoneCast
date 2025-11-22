import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Edit, Trash2, CheckCircle, XCircle } from "lucide-react";
import { buildApiUrl } from "@/lib/apiClient.js";
import { useToast } from "@/hooks/use-toast";

const apiUrl = (path) => buildApiUrl(path);

export default function PromoCodesTab({ token }) {
  const { toast } = useToast();
  const [promoCodes, setPromoCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingCode, setEditingCode] = useState(null);
  const [formData, setFormData] = useState({
    code: "",
    description: "",
    benefit_description: "",
    is_active: true,
    max_uses: "",
    expires_at: "",
    discount_percentage: "",
    bonus_credits: "",
    applies_to_monthly: true,
    applies_to_yearly: true,
  });

  useEffect(() => {
    fetchPromoCodes();
  }, []);

  const fetchPromoCodes = async () => {
    try {
      setLoading(true);
      const response = await fetch(apiUrl("/api/admin/promo-codes"), {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) throw new Error("Failed to fetch promo codes");
      const data = await response.json();
      setPromoCodes(data);
    } catch (error) {
      toast({
        title: "Error",
        description: error.message,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingCode(null);
    setFormData({
      code: "",
      description: "",
      benefit_description: "",
      is_active: true,
      max_uses: "",
      expires_at: "",
      discount_percentage: "",
      bonus_credits: "",
      applies_to_monthly: true,
      applies_to_yearly: true,
    });
    setIsDialogOpen(true);
  };

  const handleEdit = (code) => {
    setEditingCode(code);
    setFormData({
      code: code.code,
      description: code.description || "",
      benefit_description: code.benefit_description || "",
      is_active: code.is_active,
      max_uses: code.max_uses?.toString() || "",
      expires_at: code.expires_at ? code.expires_at.slice(0, 16) : "",
      discount_percentage: code.discount_percentage?.toString() || "",
      bonus_credits: code.bonus_credits?.toString() || "",
      applies_to_monthly: code.applies_to_monthly !== undefined ? code.applies_to_monthly : true,
      applies_to_yearly: code.applies_to_yearly !== undefined ? code.applies_to_yearly : true,
    });
    setIsDialogOpen(true);
  };

  const handleDelete = async (codeId) => {
    if (!confirm("Are you sure you want to delete this promo code?")) return;

    try {
      const response = await fetch(apiUrl(`/api/admin/promo-codes/${codeId}`), {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) throw new Error("Failed to delete promo code");
      toast({
        title: "Success",
        description: "Promo code deleted successfully",
      });
      fetchPromoCodes();
    } catch (error) {
      toast({
        title: "Error",
        description: error.message,
        variant: "destructive",
      });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        ...formData,
        code: formData.code.toUpperCase().trim(),
        max_uses: formData.max_uses ? parseInt(formData.max_uses) : null,
        expires_at: formData.expires_at || null,
        discount_percentage: formData.discount_percentage ? parseFloat(formData.discount_percentage) : null,
        bonus_credits: formData.bonus_credits ? parseFloat(formData.bonus_credits) : null,
        applies_to_monthly: formData.applies_to_monthly,
        applies_to_yearly: formData.applies_to_yearly,
      };

      const url = editingCode
        ? apiUrl(`/api/admin/promo-codes/${editingCode.id}`)
        : apiUrl("/api/admin/promo-codes");
      const method = editingCode ? "PATCH" : "POST";

      const response = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to save promo code");
      }

      toast({
        title: "Success",
        description: `Promo code ${editingCode ? "updated" : "created"} successfully`,
      });
      setIsDialogOpen(false);
      fetchPromoCodes();
    } catch (error) {
      toast({
        title: "Error",
        description: error.message,
        variant: "destructive",
      });
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "—";
    return new Date(dateString).toLocaleDateString();
  };

  if (loading) {
    return <div className="text-center py-12">Loading promo codes...</div>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Promo Codes</CardTitle>
              <p className="text-sm text-gray-600 mt-1">Manage referral and promotional codes</p>
            </div>
            <Button onClick={handleCreate}>
              <Plus className="w-4 h-4 mr-2" />
              Create Promo Code
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Discount</TableHead>
                <TableHead>Bonus Credits</TableHead>
                <TableHead>Applies To</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Usage</TableHead>
                <TableHead>Max Uses</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {promoCodes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={11} className="text-center text-gray-500 py-8">
                    No promo codes found. Create one to get started.
                  </TableCell>
                </TableRow>
              ) : (
                promoCodes.map((code) => (
                  <TableRow key={code.id}>
                    <TableCell className="font-mono font-semibold">{code.code}</TableCell>
                    <TableCell className="max-w-xs truncate">{code.description || "—"}</TableCell>
                    <TableCell>
                      {code.discount_percentage ? (
                        <Badge variant="outline">{code.discount_percentage}%</Badge>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      {code.bonus_credits ? (
                        <Badge variant="outline">{parseInt(code.bonus_credits).toLocaleString()}</Badge>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        {code.applies_to_monthly !== false && (
                          <Badge variant="secondary" className="text-xs">Monthly</Badge>
                        )}
                        {code.applies_to_yearly !== false && (
                          <Badge variant="secondary" className="text-xs">Yearly</Badge>
                        )}
                        {code.applies_to_monthly === false && code.applies_to_yearly === false && "—"}
                      </div>
                    </TableCell>
                    <TableCell>
                      {code.is_active ? (
                        <Badge className="bg-green-100 text-green-800">Active</Badge>
                      ) : (
                        <Badge variant="secondary">Inactive</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {code.usage_count} {code.max_uses ? `/ ${code.max_uses}` : ""}
                    </TableCell>
                    <TableCell>{code.max_uses || "Unlimited"}</TableCell>
                    <TableCell>{formatDate(code.expires_at)}</TableCell>
                    <TableCell>{formatDate(code.created_at)}</TableCell>
                    <TableCell>
                      <div className="flex items-center space-x-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(code)}
                        >
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(code.id)}
                        >
                          <Trash2 className="w-4 h-4 text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingCode ? "Edit Promo Code" : "Create Promo Code"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="code">Code *</Label>
              <Input
                id="code"
                value={formData.code}
                onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                placeholder="PROMO2024"
                required
                disabled={!!editingCode}
                maxLength={50}
              />
              {editingCode && (
                <p className="text-xs text-gray-500">Code cannot be changed after creation</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Internal description of this promo code"
                rows={2}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="benefit_description">Benefit Description</Label>
              <Textarea
                id="benefit_description"
                value={formData.benefit_description}
                onChange={(e) => setFormData({ ...formData, benefit_description: e.target.value })}
                placeholder="User-facing description of what benefit this code provides"
                rows={2}
              />
            </div>

            <div className="space-y-4 border-t pt-4">
              <div className="text-sm font-semibold">Discount & Credits</div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="discount_percentage">Discount Percentage</Label>
                  <Input
                    id="discount_percentage"
                    type="number"
                    value={formData.discount_percentage}
                    onChange={(e) => setFormData({ ...formData, discount_percentage: e.target.value })}
                    placeholder="0-100"
                    min="0"
                    max="100"
                    step="0.01"
                  />
                  <p className="text-xs text-gray-500">Percentage off subscription (0-100)</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="bonus_credits">Bonus Credits</Label>
                  <Input
                    id="bonus_credits"
                    type="number"
                    value={formData.bonus_credits}
                    onChange={(e) => setFormData({ ...formData, bonus_credits: e.target.value })}
                    placeholder="0"
                    min="0"
                    step="0.01"
                  />
                  <p className="text-xs text-gray-500">Credits to award when code is used</p>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Applies To</Label>
                <div className="flex items-center space-x-6">
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="applies_to_monthly"
                      checked={formData.applies_to_monthly}
                      onCheckedChange={(checked) => setFormData({ ...formData, applies_to_monthly: checked })}
                    />
                    <Label htmlFor="applies_to_monthly">Monthly Subscriptions</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="applies_to_yearly"
                      checked={formData.applies_to_yearly}
                      onCheckedChange={(checked) => setFormData({ ...formData, applies_to_yearly: checked })}
                    />
                    <Label htmlFor="applies_to_yearly">Yearly Subscriptions</Label>
                  </div>
                </div>
                <p className="text-xs text-gray-500">Select which billing cycles this promo code applies to</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="max_uses">Max Uses</Label>
                <Input
                  id="max_uses"
                  type="number"
                  value={formData.max_uses}
                  onChange={(e) => setFormData({ ...formData, max_uses: e.target.value })}
                  placeholder="Leave empty for unlimited"
                  min="1"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="expires_at">Expires At</Label>
                <Input
                  id="expires_at"
                  type="datetime-local"
                  value={formData.expires_at}
                  onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
                />
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
              />
              <Label htmlFor="is_active">Active</Label>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit">
                {editingCode ? "Update" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}






