import { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Loader2 } from "lucide-react";
import { makeApi, isApiError } from "@/lib/apiClient";
import CoverCropper from "./CoverCropper";

// Language options for podcast metadata
const LANG_OPTIONS = [
	{ code: "en", label: "English" },
	{ code: "es", label: "Spanish" },
	{ code: "fr", label: "French" },
	{ code: "de", label: "German" },
	{ code: "it", label: "Italian" },
	{ code: "pt", label: "Portuguese" },
	{ code: "pt-br", label: "Portuguese (Brazil)" },
	{ code: "nl", label: "Dutch" },
	{ code: "sv", label: "Swedish" },
	{ code: "no", label: "Norwegian" },
	{ code: "da", label: "Danish" },
	{ code: "fi", label: "Finnish" },
	{ code: "pl", label: "Polish" },
	{ code: "ru", label: "Russian" },
	{ code: "ja", label: "Japanese" },
	{ code: "zh", label: "Chinese" },
	{ code: "ar", label: "Arabic" },
];

export default function EditPodcastDialog({
	isOpen,
	onClose,
	podcast,
	onSave,
	token,
	userEmail,
	userFirstName,
	userLastName,
}) {
	const [formData, setFormData] = useState({
		name: "",
		description: "",
		cover_path: "",
		podcast_type: "",
		language: "",
		copyright_line: "",
		owner_name: "",
		author_name: "",
		contact_email: "",
		category_id: "",
		category_2_id: "",
		category_3_id: "",
	});
	const [categories, setCategories] = useState([]);
	const [remoteStatus, setRemoteStatus] = useState({
		loading: false,
		error: "",
		loaded: false,
	});
	const [lastRemote, setLastRemote] = useState(null);
	const [isSaving, setIsSaving] = useState(false);
	const [newCoverFile, setNewCoverFile] = useState(null);
	const [coverPreview, setCoverPreview] = useState("");
	const coverCropperRef = useRef(null);
	const [coverCrop, setCoverCrop] = useState(null);
	const [coverMode, setCoverMode] = useState('crop');
	const { toast } = useToast();

	// Validation: name should be at least 4 chars
	const nameTooShort = (formData.name || "").trim().length < 4;

	// Ensure we always present a readable error string (never [object Object])
	const toErrorText = (err) => {
		if (!err) return "";
		if (typeof err === "string") return err;
		const pick = (v) => (typeof v === "string" ? v : (v && typeof v === "object" ? JSON.stringify(v) : (v == null ? "" : String(v))));
		// Common fields returned by our API client
		const msg = err.detail || err.error || err.message || err.reason || err.msg;
		if (msg) return pick(msg);
		if (typeof err.status === 'number') return `Request failed (${err.status})`;
		return pick(err);
	};

	// Track if we've done the initial local population to avoid overwriting remote-loaded values
	const initializedFromLocal = useRef(false);
		useEffect(() => {
		if (!podcast) return;
		// If remote already loaded, don't clobber remote values
		if (remoteStatus.loaded) return;
		// Only initialize once per open lifecycle
		if (initializedFromLocal.current && isOpen) return;
		initializedFromLocal.current = true;
			// Defaults
			const detectedLang = (() => {
				try {
					const nav = navigator?.language || navigator?.languages?.[0] || '';
					if (!nav) return '';
					const lower = String(nav).toLowerCase();
					// Map en-US -> en, es-ES -> es, pt-BR pass-through
					if (lower.startsWith('pt-br')) return 'pt-br';
					const base = lower.split('-')[0];
					const allowed = new Set(["en","es","fr","de","it","pt","pt-br","nl","sv","no","da","fi","pl","ru","ja","zh","ar"]);
					return allowed.has(base) ? base : 'en';
				} catch { return 'en'; }
			})();
			const defaultLang = detectedLang || 'en';
			const defaultType = 'episodic';
			const owner = (podcast?.owner_name) || [userFirstName, userLastName].filter(Boolean).join(' ');
			const author = (podcast?.author_name) || [userFirstName, userLastName].filter(Boolean).join(' ');
			const email = podcast?.contact_email || userEmail || '';
		setFormData({
				name: podcast.name || "",
				description: podcast.description || "",
				cover_path: podcast.cover_path || "",
				podcast_type: podcast.podcast_type || defaultType,
				language: podcast.language || defaultLang,
			copyright_line: podcast.copyright_line || "",
			owner_name: owner || "",
			author_name: author || "",
			contact_email: email,
			category_id: podcast.category_id ? String(podcast.category_id) : "",
			category_2_id: podcast.category_2_id ? String(podcast.category_2_id) : "",
			category_3_id: podcast.category_3_id ? String(podcast.category_3_id) : "",
		});
		setCoverPreview(resolveCoverURL(podcast.cover_path));
	}, [podcast, remoteStatus.loaded, isOpen, userEmail]);

	// Fetch categories once
	useEffect(() => {
		async function loadCategories() {
			try {
				const api = makeApi(token);
				const data = await api.get("/api/podcasts/categories");
				setCategories(data.categories || []);
			} catch (e) {
				/* silent */
			}
		}
		if (isOpen) loadCategories();
	}, [isOpen, token]);

	const resolveCoverURL = (path) => {
		if (!path) return "";
		if (path.startsWith("http")) return path;
		const filename = path.replace(/^\/+/, "").split("/").pop();
		return `/static/media/${filename}`;
	};

	const handleChange = (e) => {
		const { id, value } = e.target;
		setFormData((prev) => ({
			...prev,
			[id]: value,
		}));
	};

	const handleSelectChange = (id, value) => {
		setFormData((prev) => ({
			...prev,
			[id]: value,
		}));
	};

	const handleCoverFileChange = (e) => {
		const file = e.target.files?.[0];
		if (file) {
			setNewCoverFile(file);
			setCoverPreview(URL.createObjectURL(file));
			setCoverCrop(null);
		}
	};

	const handleSubmit = async (e) => {
		e.preventDefault();
		if (nameTooShort) {
			toast({ title: "Name too short", description: "Podcast title must be at least 4 characters.", variant: "destructive" });
			return;
		}
		setIsSaving(true);
		try {
			let updatedPodcast;
			const api = makeApi(token);
			if (newCoverFile) {
				const data = new FormData();
				Object.entries(formData).forEach(([k, v]) => {
					if (v !== undefined && v !== null && v !== "") data.append(k, v);
				});
				try {
					const blob = await coverCropperRef.current?.getProcessedBlob?.();
					if (blob) {
						data.append("cover_image", new File([blob], "cover.jpg", { type: "image/jpeg" }));
					} else {
						data.append("cover_image", newCoverFile);
					}
				} catch {
					data.append("cover_image", newCoverFile);
				}
				updatedPodcast = await api.raw(`/api/podcasts/${podcast.id}`, { method: "PUT", body: data });
			} else {
				const payload = { ...formData };
				updatedPodcast = await api.put(`/api/podcasts/${podcast.id}`, payload);
			}

			onSave(updatedPodcast);
			toast({ title: "Success", description: "Podcast updated successfully." });
			onClose();
		} catch (error) {
			const msg = isApiError(error) ? (error.detail || error.error || error.message) : String(error);
			toast({ title: "Error", description: msg, variant: "destructive" });
		} finally {
			setIsSaving(false);
		}
	};

	return (
		<Dialog open={isOpen} onOpenChange={onClose}>
			<DialogContent className="sm:max-w-[520px] w-full md:w-[520px]">
				<DialogHeader>
					<DialogTitle>Edit Podcast</DialogTitle>
					<DialogDescription>
						Make changes to your podcast here. Click save when you're done.
					</DialogDescription>
				</DialogHeader>
				<form onSubmit={handleSubmit} className="space-y-4">
					<div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
						<div className="space-y-1">
							<Label htmlFor="name">Name</Label>
							<Input id="name" value={formData.name} onChange={handleChange} />
							{nameTooShort && <p className="text-[11px] text-amber-700">Minimum 4 characters.</p>}
						</div>
						<div className="space-y-1">
							<Label htmlFor="description">Description</Label>
							<Textarea id="description" rows={5} value={formData.description} onChange={handleChange} />
						</div>
						<div className="space-y-1">
							<Label htmlFor="podcast_type">Podcast Type</Label>
							<Select value={formData.podcast_type} onValueChange={(v) => handleSelectChange("podcast_type", v)}>
								<SelectTrigger>
									<SelectValue placeholder="Select type" />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="episodic">Episodic</SelectItem>
									<SelectItem value="serial">Serial</SelectItem>
								</SelectContent>
							</Select>
						</div>
						<div className="space-y-1">
							<Label htmlFor="language">Language</Label>
							<Select value={formData.language} onValueChange={(v) => handleSelectChange("language", v)}>
								<SelectTrigger>
									<SelectValue placeholder="Select language" />
								</SelectTrigger>
								<SelectContent className="max-h-64 overflow-y-auto">
									{LANG_OPTIONS.map((lang) => (
										<SelectItem key={lang.code} value={lang.code}>
											{lang.label}
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</div>
						<div className="space-y-1">
							<Label htmlFor="owner_name">Owner Name</Label>
							<Input id="owner_name" value={formData.owner_name} onChange={handleChange} />
						</div>
						<div className="space-y-1">
							<Label htmlFor="author_name">Author Name</Label>
							<Input id="author_name" value={formData.author_name} onChange={handleChange} />
						</div>
						<div className="space-y-1">
							<Label htmlFor="copyright_line">Copyright Line</Label>
							<Input id="copyright_line" value={formData.copyright_line} onChange={handleChange} />
						</div>
						<div className="space-y-1">
							<Label htmlFor="contact_email">Contact Email</Label>
							<Input id="contact_email" type="email" value={formData.contact_email} onChange={handleChange} />
						</div>
						<div className="space-y-1">
							<Label>Cover</Label>
							{!newCoverFile && (
								<div className="flex items-start gap-4">
									{coverPreview && (
										<img
											src={coverPreview}
											alt="cover preview"
											className="w-16 h-16 rounded object-cover border"
										/>
									)}
									<div className="flex-1 space-y-2">
										<Input type="file" accept="image/*" onChange={handleCoverFileChange} />
										<p className="text-xs text-muted-foreground">Leave blank to keep existing cover.</p>
									</div>
								</div>
							)}
							{newCoverFile && (
								<div className="space-y-2">
									<CoverCropper
										ref={coverCropperRef}
										sourceFile={newCoverFile}
										existingUrl={null}
										value={coverCrop}
										onChange={(s)=> setCoverCrop(s)}
										onModeChange={(m)=> setCoverMode(m)}
									/>
									<p className="text-[11px] text-muted-foreground">We’ll upload a square image based on your selection.</p>
								</div>
							)}
						</div>
						<div className="space-y-1">
							<Label>Categories</Label>
							<div className="space-y-1">
								{["category_id", "category_2_id", "category_3_id"].map((field, idx) => {
									const valueProp = formData[field] === "" ? undefined : String(formData[field]);
									return (
										<Select
											key={field}
											value={valueProp}
											onValueChange={(v) => {
												if (v === "__none__") {
													handleSelectChange(field, "");
												} else {
													handleSelectChange(field, v);
												}
											}}
										>
											<SelectTrigger>
												<SelectValue placeholder={idx === 0 ? "Primary category" : "Optional"} />
											</SelectTrigger>
											<SelectContent className="max-h-60 overflow-y-auto">
												{idx > 0 && <SelectItem value="__none__">(none)</SelectItem>}
												{categories.map((cat) => (
													<SelectItem key={cat.category_id} value={String(cat.category_id)}>
														{cat.name}
													</SelectItem>
												))}
											</SelectContent>
										</Select>
									);
								})}
								<p className="text-[10px] text-muted-foreground">
									Primary + up to two optional categories.
								</p>
							</div>
						</div>
						{podcast && (
							<div className="space-y-2 p-3 bg-blue-50 border border-blue-200 rounded">
								<Label className="text-sm font-semibold text-blue-900">RSS Feed URLs</Label>
								<div className="space-y-2">
									{podcast.slug && (
										<div className="space-y-1">
											<p className="text-xs text-blue-700 font-medium">Primary Feed (slug-based):</p>
											<a
												href={`https://api.podcastplusplus.com/v1/rss/${podcast.slug}/feed.xml`}
												target="_blank"
												rel="noopener noreferrer"
												className="text-xs text-blue-600 hover:underline break-all block"
											>
												https://api.podcastplusplus.com/v1/rss/{podcast.slug}/feed.xml
											</a>
										</div>
									)}

									<p className="text-[10px] text-blue-600 mt-2">
										These are your Podcast++ RSS feeds. Share these URLs with podcast directories.
									</p>
								</div>
							</div>
						)}
					</div>



					<DialogFooter>
						<Button type="button" variant="outline" onClick={onClose}>
							Cancel
						</Button>
						<Button type="submit" disabled={isSaving || nameTooShort}>
							{isSaving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : ""}
							Save changes
						</Button>
					</DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	);
}

