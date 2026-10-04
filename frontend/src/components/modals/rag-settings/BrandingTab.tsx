import React, { useState, useEffect, useRef, useId } from 'react';
import { useBrandingStore } from '../../../stores/brandingStore';
import { useUIStore } from '../../../stores/uiStore';
import type { AppTheme } from '../../../stores/uiStore';
import { Icon } from '../../shared/Icon';

interface BrandingTabProps {
  s: Record<string, string>;
}

export const BrandingTab = ({ s }: BrandingTabProps) => {
  const id = useId();
  const theme = useUIStore((st) => st.theme);
  const setTheme = useUIStore((st) => st.setTheme);
  const branding = useBrandingStore((st) => st.branding);
  const saveBranding = useBrandingStore((st) => st.saveBranding);
  const uploadLogo = useBrandingStore((st) => st.uploadLogo);
  const resetBranding = useBrandingStore((st) => st.resetBranding);
  const addToast = useUIStore((st) => st.addToast);

  const [firmName, setFirmName] = useState(branding.firm_name);
  const [primaryColor, setPrimaryColor] = useState(branding.primary_color);
  const [secondaryColor, setSecondaryColor] = useState(branding.secondary_color);
  const [accentColor, setAccentColor] = useState(branding.accent_color);
  const [saving, setSaving] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setFirmName(branding.firm_name);
    setPrimaryColor(branding.primary_color);
    setSecondaryColor(branding.secondary_color);
    setAccentColor(branding.accent_color);
  }, [branding]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveBranding({
        firm_name: firmName,
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        accent_color: accentColor,
      });
      addToast('Branding updated', 'success');
    } catch {
      addToast('Failed to save branding', 'error');
    }
    setSaving(false);
  };

  const handleLogoUpload = async (file: File) => {
    try {
      await uploadLogo(file);
      addToast('Logo uploaded', 'success');
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Logo upload failed', 'error');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleLogoUpload(file);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) handleLogoUpload(file);
  };

  const handleReset = async () => {
    try {
      await resetBranding();
      addToast('Branding reset to defaults', 'success');
    } catch {
      addToast('Failed to reset branding', 'error');
    }
  };

  return (
    <div className={s.brandingTabContent}>
      {/* Theme */}
      <div className={s.settingGroup}>
        <label className={s.settingLabel} htmlFor={`${id}-theme`}>Theme</label>
        <select
          id={`${id}-theme`}
          className={s.modalInput}
          value={theme}
          onChange={(e) => setTheme(e.target.value as AppTheme)}
        >
          <option value="default">Default (dark sidebar)</option>
          <option value="light">Light</option>
        </select>
        <div className={s.brandingUploadHint}>Saved on this device only.</div>
      </div>

      {/* Firm Name */}
      <div className={s.settingGroup}>
        <label className={s.settingLabel} htmlFor={`${id}-firm-name`}>Firm Name</label>
        <input
          id={`${id}-firm-name`}
          className={s.modalInput}
          value={firmName}
          onChange={(e) => setFirmName(e.target.value)}
          placeholder="CaseCite"
          maxLength={255}
        />
      </div>

      {/* Logo Upload */}
      <div className={s.settingGroup}>
        <label className={s.settingLabel} htmlFor={`${id}-logo`}>Logo</label>
        <div
          className={s.brandingLogoZone}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
        >
          {branding.logo_url && (
            <img src={branding.logo_url} alt="Logo" className={s.brandingLogoPreview} onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }} />
          )}
          <div className={s.brandingUploadText}>
            {branding.logo_url ? 'Click or drag to replace' : 'Click or drag to upload'}
          </div>
          <div className={s.brandingUploadHint}>PNG, JPEG, SVG, or WebP. Max 2 MB.</div>
        </div>
        <input
          id={`${id}-logo`}
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/svg+xml,image/webp"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </div>

      {/* Colors */}
      <div className={s.settingGroup}>
        <label className={s.settingLabel} htmlFor={`${id}-primary-color`}>Colors</label>

        <div className={s.brandingColorRow}>
          <span className={s.brandingColorLabel}>Primary</span>
          <input id={`${id}-primary-color`} aria-label="Primary colour" type="color" className={s.brandingColorInput} value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} />
          <input aria-label="Primary colour hex" className={s.brandingColorHex} value={primaryColor} onChange={(e) => setPrimaryColor(e.target.value)} maxLength={7} />
        </div>

        <div className={s.brandingColorRow}>
          <span className={s.brandingColorLabel}>Secondary</span>
          <input aria-label="Secondary colour" type="color" className={s.brandingColorInput} value={secondaryColor} onChange={(e) => setSecondaryColor(e.target.value)} />
          <input aria-label="Secondary colour hex" className={s.brandingColorHex} value={secondaryColor} onChange={(e) => setSecondaryColor(e.target.value)} maxLength={7} />
        </div>

        <div className={s.brandingColorRow}>
          <span className={s.brandingColorLabel}>Accent</span>
          <input aria-label="Accent colour" type="color" className={s.brandingColorInput} value={accentColor} onChange={(e) => setAccentColor(e.target.value)} />
          <input aria-label="Accent colour hex" className={s.brandingColorHex} value={accentColor} onChange={(e) => setAccentColor(e.target.value)} maxLength={7} />
        </div>

        <div className={s.brandingPreview}>
          <div className={s.brandingPreviewLabel}>Preview</div>
          <div className={s.brandingSwatchRow}>
            <div className={s.brandingSwatch} style={{ background: primaryColor }} title="Primary" />
            <div className={s.brandingSwatch} style={{ background: secondaryColor }} title="Secondary" />
            <div className={s.brandingSwatch} style={{ background: accentColor }} title="Accent" />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className={s.brandingActions}>
        <button className={s.brandingResetBtn} onClick={handleReset}>
          Reset Defaults
        </button>
        <button className={s.btnPrimary} onClick={handleSave} disabled={saving}>
          <Icon name="Save" size={14} /> {saving ? 'Saving...' : 'Save Branding'}
        </button>
      </div>
    </div>
  );
};
