import React, { useState } from 'react';
import { Mail, PenLine } from 'lucide-react';
import EmailTemplateList from '../components/settings/EmailTemplateList';
import SignatureTemplateList from '../components/settings/SignatureTemplateList';
import EmailTemplateEditor from '../components/settings/EmailTemplateEditor';
import SignatureTemplateEditor from '../components/settings/SignatureTemplateEditor';

const TABS = [
  { key: 'email', label: 'Email Templates', icon: Mail },
  { key: 'signature', label: 'Signatures', icon: PenLine },
];

/** LQ-only settings (route protected by RoleRoute + backend IsLQOnly). */
const SettingsPage = () => {
  const [tab, setTab] = useState('email');
  const [editing, setEditing] = useState(null); // { kind, id|null }
  const [refreshKey, setRefreshKey] = useState(0);

  const close = () => { setEditing(null); setRefreshKey((k) => k + 1); };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-slate-800">Settings</h1>
        <p className="text-sm text-slate-500">Design reusable email templates and signatures for your outreach.</p>
      </div>

      {editing ? (
        editing.kind === 'email' ? (
          <EmailTemplateEditor key={editing.id || 'new'} id={editing.id} onClose={close} onSaved={close} />
        ) : (
          <SignatureTemplateEditor key={editing.id || 'new'} id={editing.id} onClose={close} onSaved={close} />
        )
      ) : (
        <>
          <div className="flex gap-2 border-b border-slate-200">
            {TABS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                id={`settings-tab-${key}`}
                onClick={() => setTab(key)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-bold border-b-2 -mb-px transition ${tab === key ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-800'}`}
              >
                <Icon className="w-4 h-4" /> {label}
              </button>
            ))}
          </div>
          {tab === 'email' ? (
            <EmailTemplateList refreshKey={refreshKey} onCreate={() => setEditing({ kind: 'email', id: null })} onEdit={(id) => setEditing({ kind: 'email', id })} />
          ) : (
            <SignatureTemplateList refreshKey={refreshKey} onCreate={() => setEditing({ kind: 'signature', id: null })} onEdit={(id) => setEditing({ kind: 'signature', id })} />
          )}
        </>
      )}
    </div>
  );
};

export default SettingsPage;
