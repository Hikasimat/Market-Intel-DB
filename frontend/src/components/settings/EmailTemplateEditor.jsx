import React from 'react';
import DesignEditor from './DesignEditor';

const STARTER = `<table width="100%" cellpadding="0" cellspacing="0" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0;">
  <tr>
    <td style="padding: 32px 28px;">
      <h2 style="margin: 0 0 16px 0; color: #0f172a; font-size: 20px; font-weight: 700;">
        Hello {{contact_name}},
      </h2>
      <p style="margin: 0 0 14px 0; color: #334155; font-size: 15px; line-height: 1.6;">
        I'm reaching out from {{sender_name}} to introduce our comprehensive solutions tailored for {{company_name}}.
      </p>
      <p style="margin: 0 0 14px 0; color: #334155; font-size: 15px; line-height: 1.6;">
        We would love to schedule a brief 10-minute introductory call to explore how we can support your strategic initiatives.
      </p>
      <p style="margin: 0; color: #334155; font-size: 15px; line-height: 1.6;">
        Looking forward to hearing from you.
      </p>
    </td>
  </tr>
</table>`;

const EmailTemplateEditor = (props) => (
  <DesignEditor
    kind="email"
    noun="Template"
    starterHtml={STARTER}
    withSubject
    withDescription
    {...props}
  />
);

export default EmailTemplateEditor;
