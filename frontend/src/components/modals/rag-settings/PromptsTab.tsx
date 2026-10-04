import { useId, useState } from 'react';
import { Icon } from '../../shared/Icon';
import { api } from '../../../api';
import { useUIStore } from '../../../stores/uiStore';
import type { RagSettings } from '../../../types';
import logger from '../../../utils/logger';

interface PromptsTabProps {
  local: RagSettings;
  setLocal: (s: RagSettings) => void;
  s: Record<string, string>;
}

export const PromptsTab = ({ local, setLocal, s }: PromptsTabProps) => {
  const id = useId();
  const addToast = useUIStore((st) => st.addToast);
  const [generatingProfile, setGeneratingProfile] = useState(false);

  const handleGenerateProfile = async () => {
    const area = (local.practice_area || '').trim();
    if (!area) {
      addToast('Type your practice area first.', 'error');
      return;
    }
    setGeneratingProfile(true);
    try {
      const res = await api.generatePracticeProfile(area);
      setLocal({ ...local, practice_profile: res.profile });
      addToast('Practice profile generated — review and edit it, then Save.', 'success');
    } catch (e) {
      logger.error('practice profile generation failed', e);
      addToast(e instanceof Error ? e.message : 'Generation failed.', 'error');
    }
    setGeneratingProfile(false);
  };

  return (
  <div className={s.settingsGrid}>
    <div className={s.promptsBanner}>
      <div className={s.bannerHeader}>
        <Icon name="MessageSquare" size={16} className={s.bannerIconAmber} />
        <span className={s.bannerTitleAmber}>Custom Prompts</span>
      </div>
      <p className={s.bannerTextAmber}>
        Customize how the AI responds. Leave blank to use defaults. Changes apply to all future queries.
      </p>
    </div>

    {/* Practice Area & Profile — nothing about any practice is baked in */}
    <div className={s.settingGroupFullWidth}>
      <div className={s.promptBlockHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-practice-area`}>Your Practice</label>
        <button
          className={s.btnSecondaryXSmall}
          onClick={handleGenerateProfile}
          disabled={generatingProfile}
        >
          {generatingProfile
            ? <Icon name="Loader2" size={12} className={s.spin} />
            : <Icon name="Sparkles" size={12} />}
          {generatingProfile ? 'Generating…' : 'Generate profile'}
        </button>
      </div>
      <input
        id={`${id}-practice-area`}
        className={s.modalInput}
        value={local.practice_area || ''}
        onChange={e => setLocal({ ...local, practice_area: e.target.value || null })}
        placeholder='What do you practice? e.g. "residential landlord-tenant law in New York", "healthcare compliance", "IP litigation"'
      />
      <textarea
        aria-label="Practice profile"
        className={s.textareaMedium}
        value={local.practice_profile || ''}
        onChange={e => setLocal({ ...local, practice_profile: e.target.value || null })}
        placeholder="Generate a profile from your practice area above, or write your own — the document types you handle, the terms that matter, the red flags, the deadlines. It rides along with every review, redline, and draft."
      />
      <span className={s.helpText}>
        Nothing about any practice area is built into the product. This profile — generated for
        YOUR practice and edited by you — is what tailors every contract review, redline, and
        draft to how you actually work.
      </span>
    </div>

    {/* Contract Review Playbook */}
    <div className={s.settingGroupFullWidth}>
      <div className={s.promptBlockHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-contract-playbook`}>Contract Review Playbook</label>
      </div>
      <textarea
        id={`${id}-contract-playbook`}
        className={s.textareaMedium}
        value={local.contract_playbook || ''}
        onChange={e => setLocal({...local, contract_playbook: e.target.value || null})}
        placeholder={'Your firm\'s standing contract standards, applied to every review and redline. E.g.:\n- We usually represent the customer/tenant side\n- Never accept unlimited liability or one-sided indemnity\n- Auto-renewal requires a 60-day notice window\n- Ignore boilerplate (counterparts, severability)'}
      />
      <span className={s.helpText}>Applied automatically whenever a contract is analyzed or redlined, on top of whatever you say in the chat.</span>
    </div>

    {/* Quick Answer Prompt */}
    <div className={s.quickAnswerBlock}>
      <div className={s.promptBlockHeader}>
        <div>
          <label className={s.settingLabelBlue} htmlFor={`${id}-factual-prompt`}>Quick Answer Prompt</label>
          <span className={s.autoDetectedBadge}>Auto-detected</span>
        </div>
        <button
          className={s.btnSecondaryXSmall}
          onClick={async () => {
            try {
              const defaults = await api.getPromptDefaults() as Record<string, string>;
              setLocal({...local, custom_factual_prompt: defaults.factual_prompt});
            } catch (e) { logger.error('Failed to load defaults:', e); }
          }}
        >
          <Icon name="RotateCcw" size={12} /> Load Default
        </button>
      </div>
      <textarea
        id={`${id}-factual-prompt`}
        className={s.textareaMedium}
        value={local.custom_factual_prompt || ''}
        onChange={e => setLocal({...local, custom_factual_prompt: e.target.value || null})}
        placeholder="Leave blank for default. Used for simple factual questions like 'What was the date?' - gives brief, direct answers."
      />
      <span className={s.helpTextBlue}>Used when system auto-detects factual questions (what, when, where, who, how many). Keeps responses concise.</span>
    </div>

    {/* System Prompt */}
    <div className={s.settingGroupFullWidth}>
      <div className={s.promptBlockHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-system-prompt`}>System Prompt (Analytical Base)</label>
        <button
          className={s.btnSecondaryXSmall}
          onClick={async () => {
            try {
              const defaults = await api.getPromptDefaults() as Record<string, string>;
              setLocal({...local, custom_system_prompt: defaults.system_prompt});
            } catch (e) { logger.error('Failed to load defaults:', e); }
          }}
        >
          <Icon name="RotateCcw" size={12} /> Load Default
        </button>
      </div>
      <textarea
        id={`${id}-system-prompt`}
        className={s.textareaLarge}
        value={local.custom_system_prompt || ''}
        onChange={e => setLocal({...local, custom_system_prompt: e.target.value || null})}
        placeholder="Leave blank to use default system prompt. This controls the AI's persona and overall behavior..."
      />
      <span className={s.helpText}>Base prompt for all analytical queries. Mode-specific prompts are appended to this.</span>
    </div>

    {/* Grounding Rules */}
    <div className={s.settingGroupFullWidth}>
      <div className={s.promptBlockHeader}>
        <label className={s.settingLabel} htmlFor={`${id}-grounding-rules`}>Grounding Rules</label>
        <button
          className={s.btnSecondaryXSmall}
          onClick={async () => {
            try {
              const defaults = await api.getPromptDefaults() as Record<string, string>;
              setLocal({...local, custom_grounding_rules: defaults.grounding_rules});
            } catch (e) { logger.error('Failed to load defaults:', e); }
          }}
        >
          <Icon name="RotateCcw" size={12} /> Load Default
        </button>
      </div>
      <textarea
        id={`${id}-grounding-rules`}
        className={s.textareaSmall}
        value={local.custom_grounding_rules || ''}
        onChange={e => setLocal({...local, custom_grounding_rules: e.target.value || null})}
        placeholder="Leave blank to use default grounding rules. Controls how the AI uses document context..."
      />
      <span className={s.helpText}>Instructions for how the AI should use provided documents and cite sources</span>
    </div>

    {/* Mode-Specific Prompts */}
    <div className={s.modePromptsAccordion}>
      <details>
        <summary className={s.modePromptsSummary}>
          <Icon name="Layers" size={16} /> Analysis Mode Prompts
          <span className={s.modePromptsSummaryNote}>Customize response structure for each mode</span>
        </summary>
        <div className={s.modePromptsBody}>
          {[
            { key: 'custom_research_prompt', label: 'Legal Research Mode', icon: 'Search', placeholder: 'Default: Primary Sources, Key Findings, Recommendations' },
            { key: 'custom_case_prompt', label: 'Case Analysis Mode', icon: 'Scale', placeholder: 'Default: Factual Summary, Legal Issues, Strengths, Weaknesses, Recommendations' },
            { key: 'custom_document_prompt', label: 'Document Review Mode', icon: 'FileText', placeholder: 'Default: Documents Analyzed, Key Extractions, Quality Assessment, Action Items' },
            { key: 'custom_compliance_prompt', label: 'Compliance Mode', icon: 'ShieldCheck', placeholder: 'Default: Regulatory Framework, Compliance Status, Remediation Plan' },
            { key: 'custom_strategy_prompt', label: 'Strategy Mode', icon: 'Target', placeholder: 'Default: Case Positioning, Primary Strategy, Alternative Approaches, Risk Assessment' },
          ].map((mode: { key: string; label: string; icon: string; placeholder: string }) => {
            const modeKey = mode.key.replace('custom_', '').replace('_prompt', '');
            return (
              <div key={mode.key} className={s.settingGroup}>
                <div className={s.promptBlockHeader}>
                  <label className={s.settingLabelLarger} htmlFor={`${id}-mode-${mode.key}`}>
                    <Icon name={mode.icon} size={14} className={s.modeLabelIcon} />
                    {mode.label}
                  </label>
                  <button
                    className={s.btnSecondaryXXSmall}
                    onClick={async () => {
                      try {
                        const defaults = await api.getPromptDefaults() as Record<string, unknown>;
                        const modePrompts = defaults.mode_prompts as Record<string, string> | undefined;
                        setLocal({...local, [mode.key]: modePrompts?.[modeKey]});
                      } catch (e) { logger.error('Failed to load defaults:', e); }
                    }}
                  >
                    Load Default
                  </button>
                </div>
                <textarea
                  id={`${id}-mode-${mode.key}`}
                  className={s.textareaModePrompt}
                  value={(local[mode.key] as string) || ''}
                  onChange={e => setLocal({...local, [mode.key]: e.target.value || null})}
                  placeholder={mode.placeholder}
                />
              </div>
            );
          })}
        </div>
      </details>
    </div>

    <div className={s.resetAllWrapper}>
      <button
        className={s.btnSecondaryFullWidth}
        onClick={async () => {
          setLocal({
            ...local,
            custom_system_prompt: null,
            custom_grounding_rules: null,
            custom_factual_prompt: null,
            custom_research_prompt: null,
            custom_case_prompt: null,
            custom_document_prompt: null,
            custom_compliance_prompt: null,
            custom_strategy_prompt: null
          });
        }}
      >
        <Icon name="RotateCcw" size={14} /> Clear All Custom Prompts (Use Defaults)
      </button>
    </div>
  </div>
  );
};
