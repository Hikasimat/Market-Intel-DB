import React, { useState } from 'react';
import { Sparkles, Loader2, Wand2, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../../services/api';

const TONE_OPTIONS = [
  { value: 'professional', label: 'Professional & Executive' },
  { value: 'friendly', label: 'Warm & Conversational' },
  { value: 'concise', label: 'Short & Direct' },
  { value: 'persuasive', label: 'Value-Driven & Persuasive' },
  { value: 'followup', label: 'Polite Follow-Up' },
];

const QUICK_PROMPTS = {
  OUTREACH: [
    'Introduce our solutions tailored to their industry and request a 15-minute discovery call',
    'Highlight how we help companies in their sector streamline operations and boost ROI',
    'Write a concise executive introduction referencing their company profile and offerings',
  ],
  INBOX: [
    'Write a personalized business email introducing our team and requesting a quick call',
    'Draft a polite follow-up checking in on our previous conversation and next steps',
    'Share a clear overview of our services and ask for the right point of contact',
  ],
  CAMPAIGN: [
    'Create a high-converting personalized outreach campaign email with a clear call to action',
    'Announce our latest enterprise solutions and invite recipients to schedule a walkthrough',
    'Write a concise B2B partnership outreach message for decision-makers',
  ],
};

export default function GeminiEmailPromptBox({
  sourceContext = 'OUTREACH',
  prospect = null,
  recipientEmails = [],
  campaignName = '',
  emailSubject = '',
  emailBody = '',
  setEmailSubject,
  setEmailBody,
  disabled = false,
}) {
  const [prompt, setPrompt] = useState('');
  const [tone, setTone] = useState('professional');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  const suggestions = QUICK_PROMPTS[sourceContext] || QUICK_PROMPTS.OUTREACH;

  const primaryContact =
    prospect?.key_contacts?.find((c) => c.official_email && recipientEmails.includes(c.official_email)) ||
    prospect?.key_contacts?.[0] ||
    null;

  const handleGenerate = async (customPromptText = null) => {
    const finalPrompt = (customPromptText !== null ? customPromptText : prompt).trim();
    if (!finalPrompt) {
      toast.warning('Please enter a prompt for Gemini AI to generate your personalized email.');
      return;
    }
    if (disabled || isGenerating) return;

    setIsGenerating(true);
    try {
      const payload = {
        prompt: finalPrompt,
        source_context: sourceContext,
        tone,
        prospect_id: prospect?.id || null,
        recipient_emails: recipientEmails,
        company_name: prospect?.company_name || '',
        recipient_name: primaryContact?.contact_name || '',
        industry: prospect?.primary_industries || '',
        country: prospect?.country_head_office || '',
        campaign_name: campaignName || '',
        current_subject: emailSubject || '',
        current_body: emailBody || '',
      };

      const res = await api.post('/email-ai/generate/', payload, { timeout: 60000 });
      const data = res.data || {};
      if (data.subject && setEmailSubject) {
        setEmailSubject(data.subject);
      }
      if (data.body && setEmailBody) {
        setEmailBody(data.body);
      }
      toast.success('Personalized email generated with Gemini AI!');
    } catch (err) {
      const errMsg =
        err.response?.data?.detail ||
        err.response?.data?.error ||
        'Failed to generate email with Gemini AI.';
      toast.error(errMsg);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="bg-gradient-to-r from-indigo-50/80 via-violet-50/60 to-sky-50/80 border border-indigo-200/80 rounded-2xl p-3.5 shadow-2xs space-y-3">
      {/* Header Bar */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white flex items-center justify-center shrink-0 shadow-xs">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-extrabold text-slate-900 tracking-tight">
                Gemini AI Personalized Email Generator
              </span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-700 border border-indigo-200">
                AI Powered
              </span>
              {prospect?.company_name && (
                <span className="text-[10px] font-semibold text-slate-600 bg-white/90 px-2 py-0.5 rounded-full border border-slate-200 truncate max-w-[180px]">
                  Context: {prospect.company_name}
                </span>
              )}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs font-bold text-indigo-700 hover:text-indigo-900 px-2 py-1 rounded-lg hover:bg-white/60 transition flex items-center gap-1 cursor-pointer shrink-0"
        >
          <span>{isExpanded ? 'Hide AI' : 'Open AI Prompt'}</span>
          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      </div>

      {isExpanded && (
        <div className="space-y-2.5 pt-1">
          {/* Quick Suggestion Chips */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mr-1">
              Quick Prompts:
            </span>
            {suggestions.map((suggestion, idx) => (
              <button
                key={idx}
                type="button"
                disabled={disabled || isGenerating}
                onClick={() => {
                  setPrompt(suggestion);
                }}
                className="text-[11px] font-medium text-indigo-700 bg-white/90 hover:bg-indigo-600 hover:text-white border border-indigo-200/80 px-2.5 py-1 rounded-full transition cursor-pointer disabled:opacity-50 truncate max-w-xs"
                title={suggestion}
              >
                {suggestion}
              </button>
            ))}
          </div>

          {/* Prompt Input & Controls */}
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <textarea
                rows={2}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={disabled || isGenerating}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    handleGenerate();
                  }
                }}
                placeholder={
                  prospect?.company_name
                    ? `Write a prompt to generate a personalized email for ${prospect.company_name} (e.g. "Introduce our AI & cloud services and ask for a 15-min call next Tuesday")...`
                    : 'Write a prompt describing the personalized email you want Gemini AI to write...'
                }
                className="w-full p-2.5 bg-white border border-indigo-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition resize-none"
              />
            </div>

            <div className="flex sm:flex-col justify-between gap-2 shrink-0 sm:w-48">
              <select
                value={tone}
                onChange={(e) => setTone(e.target.value)}
                disabled={disabled || isGenerating}
                className="px-2.5 py-1.5 bg-white border border-indigo-200 rounded-xl text-xs font-semibold text-slate-700 focus:outline-none focus:border-indigo-500 cursor-pointer"
                title="Select Email Tone"
              >
                {TONE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    Tone: {t.label}
                  </option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => handleGenerate()}
                disabled={disabled || isGenerating || !prompt.trim()}
                className="px-4 py-2 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 disabled:from-slate-300 disabled:to-slate-300 text-white font-bold text-xs rounded-xl shadow-xs transition flex items-center justify-center gap-1.5 cursor-pointer disabled:cursor-not-allowed"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Generating...</span>
                  </>
                ) : (
                  <>
                    <Wand2 className="w-3.5 h-3.5" />
                    <span>Generate with AI</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
