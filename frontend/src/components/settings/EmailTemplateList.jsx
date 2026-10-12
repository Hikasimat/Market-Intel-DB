import React from 'react';
import DesignList from './DesignList';

const EmailTemplateList = (props) => (
  <DesignList kind="email" title="Email Templates" noun="Template" {...props} />
);

export default EmailTemplateList;
