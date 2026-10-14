import React, { useState, useEffect, useRef } from 'react';
import {
  Bold, Italic, Underline, AlignLeft, AlignCenter, AlignRight,
  List, ListOrdered, Link as LinkIcon, Highlighter, Palette, Sparkles,
  ChevronDown, Check, Globe, Phone, Mail, X, Square
} from 'lucide-react';
import { toast } from 'react-toastify';
import { SMART_TAGS } from './emailHtmlGenerator';

const FONT_FAMILIES = [
  { label: 'Arial', value: 'Arial, Helvetica, sans-serif' },
  { label: 'Helvetica', value: 'Helvetica, Arial, sans-serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Times New Roman', value: "'Times New Roman', Times, serif" },
  { label: 'Verdana', value: 'Verdana, Geneva, sans-serif' },
  { label: 'Trebuchet MS', value: "'Trebuchet MS', sans-serif" },
  { label: 'Courier New', value: "'Courier New', Courier, monospace" },
];

const FONT_SIZES = [
  { label: '12px', value: '12px' },
  { label: '14px', value: '14px' },
  { label: '15px (Default)', value: '15px' },
  { label: '16px', value: '16px' },
  { label: '18px', value: '18px' },
  { label: '20px (Heading)', value: '20px' },
  { label: '24px (Large)', value: '24px' },
  { label: '28px (Title)', value: '28px' },
];

const HIGHLIGHT_COLORS = [
  { name: 'Yellow', value: '#fef08a' },
  { name: 'Green', value: '#bbf7d0' },
  { name: 'Blue', value: '#bae6fd' },
  { name: 'Pink', value: '#fbcfe8' },
  { name: 'Orange', value: '#fed7aa' },
  { name: 'None', value: 'transparent' },
];

const TEXT_COLORS = [
  { name: 'Dark Slate', value: '#0f172a' },
  { name: 'Body Slate', value: '#334155' },
  { name: 'Muted', value: '#64748b' },
  { name: 'Blue', value: '#2563eb' },
  { name: 'Indigo', value: '#4f46e5' },
  { name: 'Emerald', value: '#059669' },
  { name: 'Rose', value: '#e11d48' },
];

const RichTextToolbar = ({ onFormat, onInsertTag, currentFontFamily, currentFontSize }) => {
  const [showFontMenu, setShowFontMenu] = useState(false);
  const [showSizeMenu, setShowSizeMenu] = useState(false);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [showHighlightPicker, setShowHighlightPicker] = useState(false);
  const [showBgPicker, setShowBgPicker] = useState(false);
  const [showTagMenu, setShowTagMenu] = useState(false);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [linkType, setLinkType] = useState('website'); // 'website' | 'phone' | 'email'
  const [linkUrl, setLinkUrl] = useState('');
  const [linkLabel, setLinkLabel] = useState('');
  const [linkPhone, setLinkPhone] = useState('');
  const [linkEmail, setLinkEmail] = useState('');
  const [selectedFont, setSelectedFont] = useState('Arial');
  const [selectedSize, setSelectedSize] = useState('15px');
  const toolbarRef = useRef(null);

  const closeAllPopups = () => {
    setShowFontMenu(false);
    setShowSizeMenu(false);
    setShowColorPicker(false);
    setShowHighlightPicker(false);
    setShowBgPicker(false);
    setShowTagMenu(false);
    setShowLinkModal(false);
  };

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (toolbarRef.current && !toolbarRef.current.contains(e.target)) {
        closeAllPopups();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Prevent mousedown from blurring contentEditable selection
  const handlePreventDefault = (e) => {
    e.preventDefault();
  };

  const handleCommand = (cmd, val = null) => {
    onFormat(cmd, val);
  };

  const handleOpenLinkModal = (e) => {
    e.preventDefault();
    const next = !showLinkModal;
    closeAllPopups();
    if (next) {
      const sel = window.getSelection();
      const selText = sel ? sel.toString().trim() : '';
      if (selText) {
        setLinkLabel(selText);
        if (selText.includes('@')) {
          setLinkEmail(selText.replace(/^mailto:/i, ''));
          setLinkType('email');
        } else if (/^[+\d\s().-]{7,}$/.test(selText)) {
          setLinkPhone(selText);
          setLinkType('phone');
        } else {
          setLinkType('website');
        }
      }
    }
    setShowLinkModal(next);
  };

  const handleSubmitLink = (e) => {
    e && e.preventDefault();
    if (linkType === 'website') {
      if (!linkUrl || !linkUrl.trim()) {
        toast.error('Please enter a website link URL');
        return;
      }
      let finalUrl = linkUrl.trim();
      if (!/^(https?:\/\/|mailto:|tel:|#|\/)/i.test(finalUrl)) {
        finalUrl = `https://${finalUrl}`;
      }
      const finalLabel = (linkLabel || '').trim() || finalUrl;
      onFormat('insertLinkCustom', {
        type: 'website',
        url: finalUrl,
        label: finalLabel,
      });
    } else if (linkType === 'email') {
      if (!linkEmail || !linkEmail.trim()) {
        toast.error('Please enter an email address');
        return;
      }
      const rawEmail = linkEmail.trim().replace(/^mailto:/i, '');
      const mailtoUrl = `mailto:${rawEmail}`;
      const finalLabel = (linkLabel || '').trim() || rawEmail;
      onFormat('insertLinkCustom', {
        type: 'email',
        url: mailtoUrl,
        label: finalLabel,
      });
    } else {
      if (!linkPhone || !linkPhone.trim()) {
        toast.error('Please enter a mobile number');
        return;
      }
      const rawPhone = linkPhone.trim();
      const cleanedDigits = rawPhone.replace(/[^\d+]/g, '');
      const telUrl = `tel:${cleanedDigits}`;
      onFormat('insertLinkCustom', {
        type: 'phone',
        url: telUrl,
        label: rawPhone,
      });
    }
    setShowLinkModal(false);
    setLinkUrl('');
    setLinkLabel('');
    setLinkPhone('');
    setLinkEmail('');
  };

  const activeFontObj = FONT_FAMILIES.find((f) => f.value === currentFontFamily || f.label === currentFontFamily)
    || FONT_FAMILIES.find((f) => f.label === selectedFont)
    || FONT_FAMILIES[0];

  const activeSizeObj = FONT_SIZES.find((s) => s.value === currentFontSize || s.label === currentFontSize)
    || FONT_SIZES.find((s) => s.value === selectedSize || s.label === selectedSize)
    || FONT_SIZES[2]; // '15px (Default)'

  return (
    <div
      ref={toolbarRef}
      onMouseDown={handlePreventDefault}
      className="flex flex-wrap items-center gap-1 p-1.5 bg-slate-800 text-white rounded-xl shadow-lg border border-slate-700 text-xs select-none"
    >
      {/* Font Family Dropdown */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={() => {
            const next = !showFontMenu;
            closeAllPopups();
            setShowFontMenu(next);
          }}
          className="flex items-center gap-1 px-2.5 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 text-[11px] font-medium rounded-lg border border-slate-600 focus:border-blue-400 transition cursor-pointer"
          title="Font Style"
        >
          <span className="truncate max-w-[85px]" style={{ fontFamily: activeFontObj.value }}>
            {activeFontObj.label}
          </span>
          <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
        </button>

        {showFontMenu && (
          <div
            onMouseDown={handlePreventDefault}
            className="absolute left-0 top-full mt-1.5 p-1 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl z-50 flex flex-col gap-0.5 w-48 max-h-64 overflow-y-auto"
          >
            <div className="text-[10px] font-bold text-slate-400 px-2 py-1 uppercase tracking-wider">
              Font Style
            </div>
            {FONT_FAMILIES.map((f) => {
              const isSelected = activeFontObj.value === f.value;
              return (
                <button
                  key={f.value}
                  type="button"
                  onMouseDown={handlePreventDefault}
                  onClick={() => {
                    setSelectedFont(f.label);
                    handleCommand('fontName', f.value);
                    setShowFontMenu(false);
                  }}
                  className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-left text-xs transition cursor-pointer hover:bg-slate-700 ${
                    isSelected ? 'text-blue-400 font-bold bg-slate-700/60' : 'text-slate-200'
                  }`}
                  style={{ fontFamily: f.value }}
                >
                  <span>{f.label}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-blue-400 shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Font Size Dropdown */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={() => {
            const next = !showSizeMenu;
            closeAllPopups();
            setShowSizeMenu(next);
          }}
          className="flex items-center gap-1 px-2.5 py-1 bg-slate-700 hover:bg-slate-600 text-slate-100 text-[11px] font-medium rounded-lg border border-slate-600 focus:border-blue-400 transition cursor-pointer"
          title="Font Size"
        >
          <span className="truncate max-w-[90px]">{activeSizeObj.label}</span>
          <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
        </button>

        {showSizeMenu && (
          <div
            onMouseDown={handlePreventDefault}
            className="absolute left-0 top-full mt-1.5 p-1 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl z-50 flex flex-col gap-0.5 w-40 max-h-64 overflow-y-auto"
          >
            <div className="text-[10px] font-bold text-slate-400 px-2 py-1 uppercase tracking-wider">
              Font Size
            </div>
            {FONT_SIZES.map((s) => {
              const isSelected = activeSizeObj.value === s.value;
              return (
                <button
                  key={s.value}
                  type="button"
                  onMouseDown={handlePreventDefault}
                  onClick={() => {
                    setSelectedSize(s.value);
                    handleCommand('fontSizeCustom', s.value);
                    setShowSizeMenu(false);
                  }}
                  className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-left text-xs transition cursor-pointer hover:bg-slate-700 ${
                    isSelected ? 'text-blue-400 font-bold bg-slate-700/60' : 'text-slate-200'
                  }`}
                >
                  <span style={{ fontSize: s.value }}>{s.label}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-blue-400 shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="h-4 w-px bg-slate-600 mx-0.5" />

      {/* Basic Formatting */}
      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('bold')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Bold"
      >
        <Bold className="w-3.5 h-3.5" />
      </button>

      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('italic')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Italic"
      >
        <Italic className="w-3.5 h-3.5" />
      </button>

      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('underline')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Underline"
      >
        <Underline className="w-3.5 h-3.5" />
      </button>

      <div className="h-4 w-px bg-slate-600 mx-0.5" />

      {/* Text Color Picker Toggle */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={() => {
            const next = !showColorPicker;
            closeAllPopups();
            setShowColorPicker(next);
          }}
          className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white flex items-center gap-1 transition cursor-pointer"
          title="Text Color"
        >
          <Palette className="w-3.5 h-3.5 text-blue-400" />
        </button>

        {showColorPicker && (
          <div
            className="absolute left-0 top-full mt-1.5 p-2 bg-slate-800 border border-slate-700 rounded-xl shadow-xl z-50 flex flex-col gap-1 w-36"
            onMouseDown={handlePreventDefault}
          >
            <div className="text-[10px] font-bold text-slate-400 px-1 uppercase">Text Color</div>
            <div className="grid grid-cols-4 gap-1.5 p-1">
              {TEXT_COLORS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onMouseDown={handlePreventDefault}
                  onClick={() => {
                    handleCommand('foreColor', c.value);
                    setShowColorPicker(false);
                  }}
                  className="w-6 h-6 rounded-md border border-slate-600 hover:scale-110 transition cursor-pointer"
                  style={{ backgroundColor: c.value }}
                  title={c.name}
                />
              ))}
            </div>
            <div className="pt-1 border-t border-slate-700">
              <input
                type="color"
                onChange={(e) => {
                  handleCommand('foreColor', e.target.value);
                  setShowColorPicker(false);
                }}
                className="w-full h-6 rounded cursor-pointer bg-slate-700 border border-slate-600 p-0.5"
                title="Custom color"
              />
            </div>
          </div>
        )}
      </div>

      {/* Text Highlight Picker Toggle */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={() => {
            const next = !showHighlightPicker;
            closeAllPopups();
            setShowHighlightPicker(next);
          }}
          className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white flex items-center gap-1 transition cursor-pointer"
          title="Highlight Selected Text"
        >
          <Highlighter className="w-3.5 h-3.5 text-amber-300" />
        </button>

        {showHighlightPicker && (
          <div
            className="absolute left-0 top-full mt-1.5 p-2 bg-slate-800 border border-slate-700 rounded-xl shadow-xl z-50 flex flex-col gap-1 w-40"
            onMouseDown={handlePreventDefault}
          >
            <div className="text-[10px] font-bold text-slate-400 px-1 uppercase">Highlight Text</div>
            <div className="grid grid-cols-3 gap-1.5 p-1">
              {HIGHLIGHT_COLORS.map((h) => (
                <button
                  key={h.value}
                  type="button"
                  onMouseDown={handlePreventDefault}
                  onClick={() => {
                    handleCommand('highlightCustom', h.value);
                    setShowHighlightPicker(false);
                  }}
                  className="flex items-center justify-center h-6 rounded-md border border-slate-600 text-[10px] font-bold text-slate-900 hover:scale-105 transition cursor-pointer"
                  style={{ backgroundColor: h.value === 'transparent' ? '#334155' : h.value, color: h.value === 'transparent' ? '#cbd5e1' : '#0f172a' }}
                  title={h.name}
                >
                  {h.name === 'None' ? '✕' : ''}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Text Box Background Color Picker Toggle */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={() => {
            const next = !showBgPicker;
            closeAllPopups();
            setShowBgPicker(next);
          }}
          className={`p-1.5 rounded-lg transition cursor-pointer flex items-center gap-1 ${
            showBgPicker ? 'bg-slate-700 text-blue-400' : 'hover:bg-slate-700 text-slate-200 hover:text-white'
          }`}
          title="Change Text Box Background Color"
        >
          <Square className="w-3.5 h-3.5 text-blue-400 fill-blue-400/40" />
        </button>

        {showBgPicker && (
          <div
            className="absolute left-0 top-full mt-1.5 p-2.5 bg-slate-800 border border-slate-700 rounded-xl shadow-xl z-50 flex flex-col gap-2 w-48 select-none"
            onMouseDown={handlePreventDefault}
          >
            <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              <span>Text Box Background</span>
              <button
                type="button"
                onMouseDown={handlePreventDefault}
                onClick={() => {
                  handleCommand('textBoxBackground', 'transparent');
                  setShowBgPicker(false);
                }}
                className="text-rose-400 hover:underline cursor-pointer lowercase text-[10px]"
              >
                clear
              </button>
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {['#ffffff', '#f8fafc', '#f1f5f9', '#e2e8f0', '#0f172a', '#2563eb', '#059669', '#dc2626', '#f59e0b', '#8b5cf6', '#ec4899', 'transparent'].map((bgCol) => (
                <button
                  key={bgCol}
                  type="button"
                  onMouseDown={handlePreventDefault}
                  onClick={() => {
                    handleCommand('textBoxBackground', bgCol);
                    setShowBgPicker(false);
                  }}
                  className="flex items-center justify-center h-6 rounded-md border border-slate-600 text-[10px] font-bold hover:scale-105 transition cursor-pointer shadow-xs"
                  style={{ backgroundColor: bgCol === 'transparent' ? '#334155' : bgCol, color: bgCol === 'transparent' ? '#cbd5e1' : '#0f172a' }}
                  title={bgCol}
                >
                  {bgCol === 'transparent' ? '✕' : ''}
                </button>
              ))}
            </div>
            <div className="pt-1 border-t border-slate-700">
              <input
                type="color"
                onChange={(e) => {
                  handleCommand('textBoxBackground', e.target.value);
                  setShowBgPicker(false);
                }}
                className="w-full h-6 rounded cursor-pointer bg-slate-700 border border-slate-600 p-0.5"
                title="Custom color"
              />
            </div>
          </div>
        )}
      </div>

      <div className="h-4 w-px bg-slate-600 mx-0.5" />

      {/* Alignments */}
      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('justifyLeft')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Align Left"
      >
        <AlignLeft className="w-3.5 h-3.5" />
      </button>

      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('justifyCenter')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Align Center"
      >
        <AlignCenter className="w-3.5 h-3.5" />
      </button>

      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('justifyRight')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Align Right"
      >
        <AlignRight className="w-3.5 h-3.5" />
      </button>

      <div className="h-4 w-px bg-slate-600 mx-0.5" />

      {/* Lists */}
      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('insertUnorderedList')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Bulleted List"
      >
        <List className="w-3.5 h-3.5" />
      </button>

      <button
        type="button"
        onMouseDown={handlePreventDefault}
        onClick={() => handleCommand('insertOrderedList')}
        className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-200 hover:text-white transition cursor-pointer"
        title="Numbered List"
      >
        <ListOrdered className="w-3.5 h-3.5" />
      </button>

      {/* Link Button & Popover Modal */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={handleOpenLinkModal}
          className={`p-1.5 rounded-lg transition cursor-pointer ${
            showLinkModal ? 'bg-slate-700 text-blue-400' : 'hover:bg-slate-700 text-slate-200 hover:text-white'
          }`}
          title="Insert Link (Website or Mobile Number)"
        >
          <LinkIcon className="w-3.5 h-3.5" />
        </button>

        {showLinkModal && (
          <div
            className="absolute left-0 top-full mt-2 p-3 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl z-50 w-80 text-white select-none animate-fade-in"
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
              <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                Insert Link
              </span>
              <button
                type="button"
                onClick={() => setShowLinkModal(false)}
                className="text-slate-400 hover:text-white p-0.5 rounded cursor-pointer transition"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Tabs: Website vs Mobile No vs Mail Link */}
            <div className="grid grid-cols-3 gap-1 p-0.5 bg-slate-800 rounded-xl mb-3 text-xs font-bold">
              <button
                type="button"
                onClick={() => setLinkType('website')}
                className={`py-1.5 px-2 rounded-lg flex items-center justify-center gap-1 transition cursor-pointer ${
                  linkType === 'website'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Globe className="w-3.5 h-3.5" />
                <span>Website</span>
              </button>
              <button
                type="button"
                onClick={() => setLinkType('phone')}
                className={`py-1.5 px-2 rounded-lg flex items-center justify-center gap-1 transition cursor-pointer ${
                  linkType === 'phone'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Phone className="w-3.5 h-3.5" />
                <span>Mobile No</span>
              </button>
              <button
                type="button"
                onClick={() => setLinkType('email')}
                className={`py-1.5 px-2 rounded-lg flex items-center justify-center gap-1 transition cursor-pointer ${
                  linkType === 'email'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Mail className="w-3.5 h-3.5" />
                <span>Mail Link</span>
              </button>
            </div>

            {linkType === 'website' ? (
              <div className="space-y-2.5">
                <div>
                  <label className="block text-[11px] font-bold text-slate-300 mb-1">
                    Website Link <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={linkUrl}
                    onChange={(e) => setLinkUrl(e.target.value)}
                    placeholder="e.g. https://plusuae.com or www.google.com"
                    className="w-full p-2 bg-slate-800 border border-slate-700 focus:border-blue-500 rounded-xl text-xs text-white placeholder-slate-500 outline-none"
                    autoFocus
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-300 mb-1">
                    Link Label (Display Text) <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={linkLabel}
                    onChange={(e) => setLinkLabel(e.target.value)}
                    placeholder="e.g. Visit Our Website / Click Here"
                    className="w-full p-2 bg-slate-800 border border-slate-700 focus:border-blue-500 rounded-xl text-xs text-white placeholder-slate-500 outline-none"
                  />
                </div>

                <p className="text-[10px] text-slate-400 leading-tight">
                  Redirects to this page when clicked in the created email draft without underlines.
                </p>
              </div>
            ) : linkType === 'email' ? (
              <div className="space-y-2.5">
                <div>
                  <label className="block text-[11px] font-bold text-slate-300 mb-1">
                    Email Address <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="email"
                    value={linkEmail}
                    onChange={(e) => setLinkEmail(e.target.value)}
                    placeholder="e.g. info@plusuae.com"
                    className="w-full p-2 bg-slate-800 border border-slate-700 focus:border-blue-500 rounded-xl text-xs text-white placeholder-slate-500 outline-none"
                    autoFocus
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-300 mb-1">
                    Link Label (Display Text)
                  </label>
                  <input
                    type="text"
                    value={linkLabel}
                    onChange={(e) => setLinkLabel(e.target.value)}
                    placeholder="Leave blank to use email address"
                    className="w-full p-2 bg-slate-800 border border-slate-700 focus:border-blue-500 rounded-xl text-xs text-white placeholder-slate-500 outline-none"
                  />
                </div>

                <p className="text-[10px] text-slate-400 leading-tight">
                  Opens default email application when clicked without underlines.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                <div>
                  <label className="block text-[11px] font-bold text-slate-300 mb-1">
                    Mobile Number <span className="text-rose-400">*</span>
                  </label>
                  <input
                    type="text"
                    value={linkPhone}
                    onChange={(e) => setLinkPhone(e.target.value)}
                    placeholder="e.g. +971 50 123 4567 or 9876543210"
                    className="w-full p-2 bg-slate-800 border border-slate-700 focus:border-blue-500 rounded-xl text-xs text-white placeholder-slate-500 outline-none"
                    autoFocus
                  />
                </div>

                <div className="p-2 rounded-xl bg-slate-800/80 border border-slate-700/60 text-[10px] text-slate-300">
                  ℹ️ <span className="font-semibold text-slate-200">No label needed</span> — the mobile number will be displayed as the link and will open the phone dialer when clicked.
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-end gap-2 pt-3 mt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowLinkModal(false)}
                className="px-2.5 py-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 text-xs font-semibold transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitLink}
                className="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition shadow-xs cursor-pointer"
              >
                Insert Link
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="h-4 w-px bg-slate-600 mx-0.5" />

      {/* Insert Smart Tag Quick Menu */}
      <div className="relative">
        <button
          type="button"
          onMouseDown={handlePreventDefault}
          onClick={() => {
            const next = !showTagMenu;
            closeAllPopups();
            setShowTagMenu(next);
          }}
          className="px-2 py-1 rounded-lg bg-indigo-600/60 hover:bg-indigo-600 text-indigo-100 font-bold text-[11px] flex items-center gap-1 transition cursor-pointer"
          title="Insert Personalization Smart Tag"
        >
          <Sparkles className="w-3 h-3 text-indigo-300" />
          <span>Smart Tag</span>
        </button>

        {showTagMenu && (
          <div
            className="absolute right-0 top-full mt-1.5 p-1.5 bg-slate-800 border border-slate-700 rounded-xl shadow-xl z-50 flex flex-col gap-1 w-48"
            onMouseDown={handlePreventDefault}
          >
            <div className="text-[10px] font-bold text-slate-400 px-2 py-1 uppercase border-b border-slate-700">
              Insert Tag At Cursor
            </div>
            {SMART_TAGS.map((t) => (
              <button
                key={t.key}
                type="button"
                onMouseDown={handlePreventDefault}
                onClick={() => {
                  onInsertTag(t.token);
                  setShowTagMenu(false);
                }}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-700 text-left text-xs text-slate-200 hover:text-white transition cursor-pointer"
              >
                <span>{t.icon}</span>
                <span className="font-medium">{t.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default RichTextToolbar;
