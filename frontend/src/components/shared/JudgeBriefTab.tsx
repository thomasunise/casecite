import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import { cleanMarkdown } from '../../utils/markdownUtils';
import type { JudgeIntelProfile, JudgeMessage } from '../../types';

interface JudgeBriefTabProps {
  s: Record<string, string>;
  judgeIntelProfile: JudgeIntelProfile;
  judgeBrief: string | null;
  judgeBriefLoading: boolean;
  generateJudgeBrief: (profile: JudgeIntelProfile) => void;
  judgeMessages: JudgeMessage[];
  setJudgeQueryInput: (value: string) => void;
  judgeQueryLoading: boolean;
  judgeQueryIncludeDocs: boolean;
  clearJudgeConversation: () => void;
}

function JudgeBriefTab({
  s,
  judgeIntelProfile,
  judgeBrief,
  judgeBriefLoading,
  generateJudgeBrief,
  judgeMessages,
  setJudgeQueryInput,
  judgeQueryLoading,
  judgeQueryIncludeDocs,
  clearJudgeConversation,
}: JudgeBriefTabProps) {
  return (
    <div className={s.judgeBriefContent}>
      {/* Generated Brief */}
      <div className={s.judgeProfileSection}>
        <h3 className={s.judgeProfileSectionTitle}>Judicial Profile Brief</h3>
        {judgeBriefLoading ? (
          <div className={s.judgeBriefLoading}>
            <Icon name="Loader2" size={20} className={s.buildingSpinner} />
            <span className={s.briefLoadingTitle}>Analyzing judge data and generating brief...</span>
            <span className={s.briefLoadingSubtitle}>This may take 30-60 seconds</span>
          </div>
        ) : judgeBrief ? (
          <>
            <div className={s.judgeBriefText}>
              {judgeBrief.split('\n').map((line: string, i: number) => {
                const trimmedLine = line.trim();
                if (!trimmedLine) return <div key={i} className={s.briefSpacer} />;

                // Main headers (## or ### SECTION)
                if (trimmedLine.match(/^#{2,3}\s+/)) {
                  return <h2 key={i} className={s.briefH2}>{cleanMarkdown(trimmedLine)}</h2>;
                }
                // Bold-only lines as headers
                if (trimmedLine.startsWith('**') && trimmedLine.endsWith('**') && !trimmedLine.slice(2, -2).includes('**')) {
                  return <h3 key={i} className={s.briefH3}>{cleanMarkdown(trimmedLine)}</h3>;
                }
                // Single hash headers
                if (trimmedLine.match(/^#\s+/)) {
                  return <h3 key={i} className={s.briefH3}>{cleanMarkdown(trimmedLine)}</h3>;
                }
                // Numbered sections (like "1." or "1)")
                if (trimmedLine.match(/^\d+[.)]\s*/)) {
                  return <h4 key={i} className={s.briefH4}>{cleanMarkdown(trimmedLine)}</h4>;
                }
                // Bullet points
                if (trimmedLine.startsWith('- ') || trimmedLine.startsWith('* ')) {
                  return <div key={i} className={s.briefBullet}><span className={s.briefBulletDot}>•</span><span>{cleanMarkdown(trimmedLine.substring(2))}</span></div>;
                }
                // Regular paragraphs
                return <p key={i} className={s.briefParagraph}>{cleanMarkdown(trimmedLine)}</p>;
              })}
              <AiNotice />
            </div>
            <button className={s.judgeBriefRegenBtn} onClick={() => generateJudgeBrief(judgeIntelProfile)}>
              <Icon name="RefreshCw" size={12} /> Regenerate
            </button>
          </>
        ) : (
          <div className={s.judgeBriefPlaceholder}>
            <div>
              <span className={s.placeholderTitle}>AI-Generated Intelligence Brief</span>
              <span className={s.placeholderDesc}>
                An analysis of this judge's background, judicial philosophy, ruling patterns, and practice tips. Uses AI tokens · takes 30-60 seconds.
              </span>
            </div>
            <button
              onClick={() => generateJudgeBrief(judgeIntelProfile)}
              className={s.generateBriefBtn}
            >
              <Icon name="Sparkles" size={14} /> Generate Brief
            </button>
          </div>
        )}
      </div>

      {/* Ask About This Judge — the input itself is the app-wide floating
          composer rendered by the view; this section holds the conversation. */}
      <div className={s.judgeProfileSection}>
        <div className={s.judgeQaHeader}>
          <h3 className={s.judgeProfileSectionTitle}>Ask About This Judge</h3>
          {judgeMessages.length > 0 && (
            <button
              className={s.judgeQaClear}
              onClick={clearJudgeConversation}
              disabled={judgeQueryLoading}
              title="Clear the conversation and start fresh"
            >
              <Icon name="Eraser" size={12} /> Clear
            </button>
          )}
        </div>

        {judgeMessages.length > 0 ? (
          <div className={s.judgeQueryMessages}>
            {judgeMessages.map((msg: JudgeMessage) => (
              <div key={msg.id} className={`${s.judgeQueryMessage} ${msg.type === 'user' ? s.judgeQueryUserMsg : s.judgeQueryAssistantMsg}`}>
                <div className={s.judgeQueryMsgContent}>
                  {msg.type === 'assistant' ? msg.content.split('\n').map((line: string, li: number) => {
                    const clean = cleanMarkdown(line);
                    if (!clean) return <br key={li} />;
                    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) return <div key={li} className={s.msgBullet}>• {clean.substring(2)}</div>;
                    return <div key={li} className={s.msgLine}>{clean}</div>;
                  }) : msg.content}
                  {msg.type === 'assistant' && <AiNotice />}
                </div>
              </div>
            ))}
            {judgeQueryLoading && (
              <div className={`${s.judgeQueryMessage} ${s.judgeQueryAssistantMsg}`}>
                <div className={s.judgeQueryMsgContent}>
                  <Icon name="Loader2" size={14} className={s.spinnerIcon} /> Thinking...
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className={s.judgeQueryHints}>
            <span>Try asking:</span>
            {(judgeQueryIncludeDocs
              ? ['How would this judge likely rule on my case?', 'Compare this judge to cases in my documents', 'What should I know before appearing before this judge?']
              : ['What is their judicial philosophy?', 'How do they typically rule on immigration cases?', 'What are their most influential decisions?']
            ).map((hint: string, i: number) => (
              <button key={i} className={s.judgeQueryHint} onClick={() => setJudgeQueryInput(hint)}>
                {hint}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export { JudgeBriefTab };
export default JudgeBriefTab;
