import React, { useRef, useState } from 'react';
import {
  Upload, Trash2, Sliders, Type, Image as ImageIcon,
  Square, Minus, Space, Columns2, PenTool, LayoutTemplate,
  Check, Palette, Globe, Phone, Mail, Link as LinkIcon
} from 'lucide-react';
import { designApi } from '../../../services/designApi';
import { toast } from 'react-toastify';
import { resolveImageUrl } from './emailHtmlGenerator';
import { COLUMN_LAYOUTS } from './ColumnLayoutPicker';

const PRESET_COLORS = [
  '#ffffff', '#f8fafc', '#f1f5f9', '#e2e8f0', '#0f172a',
  '#2563eb', '#1d4ed8', '#4f46e5', '#059669', '#dc2626', '#f59e0b',
];

const PropertiesPanel = ({
  selectedBlock,
  selectedColumnId,
  selectedSubElementId,
  onUpdateBlock,
  onUpdateSubElement,
  onUpdateColumn,
  onDeleteBlock,
  onOpenSignatureBuilder,
  savedSignatures = [],
  onChangeBlockLayout,
  onAddElementToColumn,
  onFormatText,
}) => {
  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  if (!selectedBlock) {
    return (
      <div className="p-6 text-center text-slate-400 space-y-2">
        <Sliders className="w-8 h-8 mx-auto opacity-40 text-slate-400" />
        <div className="text-xs font-bold text-slate-600">No Element Selected</div>
        <p className="text-[11px] text-slate-400 leading-relaxed">
          Click any text, image, button, column, or section on the canvas to configure its settings.
        </p>
      </div>
    );
  }

  // Determine if we're editing a block or an element inside a column
  let activeElement = selectedBlock;
  let isSubElement = false;
  if (selectedBlock.type === 'columns' && selectedSubElementId) {
    for (const col of (selectedBlock.columns || [])) {
      for (const el of (col.elements || [])) {
        if (el.id === selectedSubElementId) {
          activeElement = el;
          isSubElement = true;
          break;
        }
        if (el.type === 'row') {
          for (const rCol of (el.columns || [])) {
            const foundNested = (rCol.elements || []).find((ne) => ne.id === selectedSubElementId);
            if (foundNested) {
              activeElement = foundNested;
              isSubElement = true;
              break;
            }
          }
        }
      }
      if (isSubElement) break;
    }
  }

  const activeColumn = selectedBlock?.type === 'columns' && selectedColumnId && !isSubElement
    ? (selectedBlock.columns || []).find((c) => c.id === selectedColumnId)
    : null;

  const updateProp = (key, val) => {
    if (isSubElement) {
      onUpdateSubElement(selectedBlock.id, selectedColumnId, activeElement.id, { [key]: val });
    } else {
      onUpdateBlock(selectedBlock.id, { [key]: val });
    }
  };

  const updateColumnProp = (key, val) => {
    if (selectedColumnId && onUpdateColumn) {
      onUpdateColumn(selectedBlock.id, selectedColumnId, { [key]: val });
    } else if (selectedColumnId && onUpdateBlock) {
      const cols = (selectedBlock.columns || []).map((c) =>
        c.id === selectedColumnId ? { ...c, [key]: val } : c
      );
      onUpdateBlock(selectedBlock.id, { columns: cols });
    }
  };

  const updateBorder = (key, val) => {
    const cur = activeElement.border || { enabled: false, color: '#e2e8f0', width: 1 };
    updateProp('border', { ...cur, [key]: val });
  };

  // Handle image file upload to backend
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      toast.error('Please choose a valid image file (JPEG, PNG, GIF, WebP).');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image size must be less than 5 MB.');
      return;
    }

    setUploading(true);
    try {
      const res = await designApi.uploadImage('email', file);
      if (res.url) {
        updateProp('url', res.url);
        toast.success('Image uploaded successfully!');
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to upload image.');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const getElementHeader = () => {
    switch (activeElement.type) {
      case 'header': return { icon: LayoutTemplate, title: 'Header Section' };
      case 'text': return { icon: Type, title: 'Text Element' };
      case 'image': return { icon: ImageIcon, title: 'Image Element' };
      case 'button': return { icon: Square, title: 'Button Element' };
      case 'divider': return { icon: Minus, title: 'Divider Line' };
      case 'spacer': return { icon: Space, title: 'Spacer Space' };
      case 'columns': return { icon: Columns2, title: 'Column Layout' };
      case 'signature': return { icon: PenTool, title: 'Signature Block' };
      case 'footer': return { icon: LayoutTemplate, title: 'Footer Section' };
      default: return { icon: Sliders, title: 'Element Settings' };
    }
  };

  const header = getElementHeader();
  const Icon = header.icon;

  return (
    <div className="p-4 space-y-4 text-xs">
      {/* Header with Type & Delete */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2 font-bold text-slate-800">
          <div className="p-1.5 rounded-lg bg-blue-50 text-blue-600">
            <Icon className="w-4 h-4" />
          </div>
          <span>{header.title}</span>
        </div>

        <button
          type="button"
          onClick={() => onDeleteBlock(selectedBlock.id, selectedColumnId, isSubElement ? activeElement.id : null)}
          className="p-1.5 rounded-lg text-rose-500 hover:text-rose-700 hover:bg-rose-50 transition"
          title="Delete element"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* --- HEADER SETTINGS --- */}
      {activeElement.type === 'header' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1">Header Title</label>
            <input
              type="text"
              value={activeElement.title || ''}
              onChange={(e) => updateProp('title', e.target.value)}
              placeholder="e.g. Monthly Market Intelligence Report"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Subtitle (Optional)</label>
            <input
              type="text"
              value={activeElement.subtitle || ''}
              onChange={(e) => updateProp('subtitle', e.target.value)}
              placeholder="e.g. Prepared for {{company_name}}"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Logo URL (Optional)</label>
            <input
              type="text"
              value={activeElement.logoUrl || ''}
              onChange={(e) => updateProp('logoUrl', e.target.value)}
              placeholder="https://..."
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs mb-1.5"
            />
            {activeElement.logoUrl && (
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-slate-500">Logo Width:</span>
                <input
                  type="number"
                  min="40"
                  max="300"
                  value={activeElement.logoWidth || 120}
                  onChange={(e) => updateProp('logoWidth', Number(e.target.value))}
                  className="w-20 p-1.5 border border-slate-200 rounded-lg text-xs"
                />
                <span className="text-slate-400 text-[10px]">px</span>
              </div>
            )}
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Alignment</label>
            <div className="grid grid-cols-3 gap-1">
              {['left', 'center', 'right'].map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => updateProp('align', a)}
                  className={`py-1.5 rounded-lg border capitalize font-semibold transition ${
                    activeElement.align === a
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* --- TEXT SETTINGS --- */}
      {activeElement.type === 'text' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1">Font Style (Family)</label>
            <select
              value={activeElement.fontFamily || 'Arial, Helvetica, sans-serif'}
              onChange={(e) => {
                const val = e.target.value;
                if (onFormatText) {
                  onFormatText('fontFamily', val);
                } else {
                  updateProp('fontFamily', val);
                }
              }}
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs cursor-pointer font-medium"
            >
              <option value="Arial, Helvetica, sans-serif">Arial</option>
              <option value="Helvetica, Arial, sans-serif">Helvetica</option>
              <option value="Georgia, serif">Georgia</option>
              <option value="'Times New Roman', Times, serif">Times New Roman</option>
              <option value="Verdana, Geneva, sans-serif">Verdana</option>
              <option value="'Trebuchet MS', sans-serif">Trebuchet MS</option>
              <option value="'Courier New', Courier, monospace">Courier New</option>
            </select>
          </div>

          <div>
            <div className="flex justify-between font-bold text-slate-600 mb-1">
              <span>Font Size</span>
              <span className="text-slate-400 font-normal">{activeElement.fontSize || 15}px</span>
            </div>
            <input
              type="range"
              min="10"
              max="36"
              step="1"
              value={activeElement.fontSize || 15}
              onChange={(e) => {
                const num = Number(e.target.value);
                if (onFormatText) {
                  onFormatText('fontSizeCustom', `${num}px`);
                } else {
                  updateProp('fontSize', num);
                }
              }}
              className="w-full accent-blue-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
              <span>10px</span>
              <span>15px (Default)</span>
              <span>24px</span>
              <span>36px</span>
            </div>
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Text Alignment</label>
            <div className="grid grid-cols-3 gap-1">
              {['left', 'center', 'right'].map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => updateProp('align', a)}
                  className={`py-1.5 rounded-lg border capitalize font-semibold transition cursor-pointer ${
                    (activeElement.align || 'left') === a
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Text Color</label>
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
              {['#0f172a', '#334155', '#64748b', '#2563eb', '#1d4ed8', '#4f46e5', '#059669', '#dc2626', '#f59e0b', '#7c3aed'].map((c) => (
                <button
                  key={c}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault(); // Keep text selection active!
                  }}
                  onClick={() => {
                    if (onFormatText) {
                      onFormatText('foreColor', c);
                    } else {
                      updateProp('color', c);
                    }
                  }}
                  className="w-5 h-5 rounded-md border border-slate-300 hover:scale-110 transition flex items-center justify-center cursor-pointer shadow-2xs"
                  style={{ backgroundColor: c }}
                  title={`Set text color: ${c}`}
                >
                  {activeElement.color === c && (
                    <Check className={`w-3 h-3 ${c === '#0f172a' ? 'text-white' : 'text-slate-800'}`} />
                  )}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={activeElement.color && activeElement.color.startsWith('#') ? activeElement.color : '#334155'}
                onChange={(e) => {
                  const col = e.target.value;
                  if (onFormatText) {
                    onFormatText('foreColor', col);
                  } else {
                    updateProp('color', col);
                  }
                }}
                className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200 p-0.5 bg-white"
              />
              <input
                type="text"
                value={activeElement.color || '#334155'}
                onChange={(e) => {
                  const col = e.target.value;
                  if (onFormatText) {
                    onFormatText('foreColor', col);
                  } else {
                    updateProp('color', col);
                  }
                }}
                className="flex-1 p-2 border border-slate-200 rounded-xl bg-white text-xs font-mono"
              />
            </div>
          </div>

          {/* Text Box Background Color */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block font-bold text-slate-700 text-xs">Text Box Background Color</label>
              {activeElement.backgroundColor && activeElement.backgroundColor !== 'transparent' && (
                <button
                  type="button"
                  onClick={() => updateProp('backgroundColor', 'transparent')}
                  className="text-[10px] text-rose-600 hover:underline font-semibold cursor-pointer"
                >
                  Clear Background
                </button>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => updateProp('backgroundColor', c)}
                  className="w-5 h-5 rounded-md border border-slate-300 hover:scale-110 transition flex items-center justify-center cursor-pointer shadow-2xs"
                  style={{ backgroundColor: c }}
                  title={`Set text box background: ${c}`}
                >
                  {activeElement.backgroundColor === c && (
                    <Check className={`w-3 h-3 ${c === '#0f172a' ? 'text-white' : 'text-slate-800'}`} />
                  )}
                </button>
              ))}
              <button
                type="button"
                onClick={() => updateProp('backgroundColor', 'transparent')}
                className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                Clear
              </button>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={activeElement.backgroundColor && activeElement.backgroundColor.startsWith('#') ? activeElement.backgroundColor : '#ffffff'}
                onChange={(e) => updateProp('backgroundColor', e.target.value)}
                className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200 p-0.5 bg-white"
              />
              <input
                type="text"
                value={activeElement.backgroundColor || 'transparent'}
                onChange={(e) => updateProp('backgroundColor', e.target.value)}
                placeholder="transparent or #hex"
                className="flex-1 p-2 border border-slate-200 rounded-xl bg-white text-xs font-mono"
              />
            </div>
          </div>

          {/* Quick Insert Link into Text */}
          <div className="pt-2 border-t border-slate-100">
            <label className="block font-bold text-slate-700 mb-1.5 flex items-center gap-1.5">
              <LinkIcon className="w-3.5 h-3.5 text-blue-600" />
              <span>Insert Link into Text</span>
            </label>
            <div className="grid grid-cols-3 gap-1.5">
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  const sel = window.getSelection();
                  const selectedText = sel && !sel.isCollapsed ? sel.toString().trim() : '';
                  const url = window.prompt('Enter website link URL (e.g. https://plusuae.com or www...):', 'https://');
                  if (!url || !url.trim()) return;
                  const label = window.prompt('Enter link label / display text:', selectedText || 'Visit Website') || url;
                  let finalUrl = url.trim();
                  if (!/^(https?:\/\/|mailto:|tel:|#|\/)/i.test(finalUrl)) finalUrl = `https://${finalUrl}`;
                  const display = label.trim() || finalUrl;
                  if (onFormatText) {
                    onFormatText('insertLinkCustom', { type: 'website', url: finalUrl, label: display });
                  } else {
                    const linkHtml = `<a href="${finalUrl}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">${display}</a>`;
                    updateProp('content', `${activeElement.content || ''} ${linkHtml} `);
                  }
                  toast.success(`Added website link "${display}"`);
                }}
                className="py-1.5 px-1.5 rounded-xl border border-slate-200 hover:border-blue-500 hover:bg-blue-50 text-slate-700 hover:text-blue-700 text-[10px] font-bold flex items-center justify-center gap-1 transition cursor-pointer"
                title="Add website link (asks for URL and label)"
              >
                <Globe className="w-3 h-3 text-blue-600 shrink-0" />
                <span className="truncate">+ Website</span>
              </button>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  const sel = window.getSelection();
                  const selectedText = sel && !sel.isCollapsed ? sel.toString().trim() : '';
                  const phone = window.prompt('Enter mobile number (e.g. +971 50 123 4567 or 9876543210):', selectedText || '');
                  if (!phone || !phone.trim()) return;
                  const rawPhone = phone.trim();
                  const cleaned = rawPhone.replace(/[^\d+]/g, '');
                  const telUrl = `tel:${cleaned}`;
                  if (onFormatText) {
                    onFormatText('insertLinkCustom', { type: 'phone', url: telUrl, label: rawPhone });
                  } else {
                    const linkHtml = `<a href="${telUrl}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">${rawPhone}</a>`;
                    updateProp('content', `${activeElement.content || ''} ${linkHtml} `);
                  }
                  toast.success(`Added mobile link ${rawPhone}`);
                }}
                className="py-1.5 px-1.5 rounded-xl border border-slate-200 hover:border-emerald-500 hover:bg-emerald-50 text-slate-700 hover:text-emerald-700 text-[10px] font-bold flex items-center justify-center gap-1 transition cursor-pointer"
                title="Add mobile number link"
              >
                <Phone className="w-3 h-3 text-emerald-600 shrink-0" />
                <span className="truncate">+ Mobile</span>
              </button>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  const sel = window.getSelection();
                  const selectedText = sel && !sel.isCollapsed ? sel.toString().trim() : '';
                  const email = window.prompt('Enter email address (e.g. fahad@vortexcx.com):', selectedText && selectedText.includes('@') ? selectedText : '');
                  if (!email || !email.trim()) return;
                  const label = window.prompt('Enter link label / display text (leave blank for email):', selectedText || email.trim()) || email.trim();
                  const cleanEmail = email.trim().replace(/^mailto:/i, '');
                  const mailtoUrl = `mailto:${cleanEmail}`;
                  const display = label.trim() || cleanEmail;
                  if (onFormatText) {
                    onFormatText('insertLinkCustom', { type: 'email', url: mailtoUrl, label: display });
                  } else {
                    const linkHtml = `<a href="${mailtoUrl}" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: none;">${display}</a>`;
                    updateProp('content', `${activeElement.content || ''} ${linkHtml} `);
                  }
                  toast.success(`Added mail link ${display}`);
                }}
                className="py-1.5 px-1.5 rounded-xl border border-slate-200 hover:border-violet-500 hover:bg-violet-50 text-slate-700 hover:text-violet-700 text-[10px] font-bold flex items-center justify-center gap-1 transition cursor-pointer"
                title="Add mailto link (asks for email address)"
              >
                <Mail className="w-3 h-3 text-violet-600 shrink-0" />
                <span className="truncate">+ Mail Link</span>
              </button>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">
              Links open the related page, phone dialer, or email composer without underlines.
            </p>
          </div>
        </div>
      )}

      {/* --- IMAGE SETTINGS --- */}
      {activeElement.type === 'image' && (
        <div className="space-y-3">
          {/* File Upload Button */}
          <div>
            <label className="block font-bold text-slate-600 mb-1.5">Upload Image</label>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
              className="w-full py-2.5 px-3 border border-dashed border-blue-300 hover:border-blue-500 rounded-xl bg-blue-50/50 hover:bg-blue-50 text-blue-600 font-bold flex items-center justify-center gap-2 transition cursor-pointer"
            >
              <Upload className="w-4 h-4" />
              <span>{uploading ? 'Uploading...' : 'Choose Image File'}</span>
            </button>
          </div>

          {activeElement.url && (
            <div className="p-2 border border-slate-200 rounded-xl bg-slate-50 flex items-center gap-2.5">
              <img
                src={resolveImageUrl(activeElement.url)}
                alt="Preview"
                className="w-10 h-10 object-contain rounded-lg border border-slate-200 bg-white p-0.5 shrink-0"
              />
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold text-slate-700 truncate">Image Attached</div>
                <div className="text-[10px] text-slate-400 truncate">{activeElement.url}</div>
              </div>
            </div>
          )}

          <div>
            <label className="block font-bold text-slate-600 mb-1">Or Image URL</label>
            <input
              type="text"
              value={activeElement.url || ''}
              onChange={(e) => updateProp('url', e.target.value)}
              placeholder="https://example.com/image.png"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <div className="flex justify-between font-bold text-slate-600 mb-1">
              <span>Width</span>
              <span className="text-slate-400 font-normal">{activeElement.width || 320}px</span>
            </div>
            <input
              type="range"
              min="60"
              max="580"
              step="10"
              value={activeElement.width || 320}
              onChange={(e) => updateProp('width', Number(e.target.value))}
              className="w-full accent-blue-600 cursor-pointer"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Alignment</label>
            <div className="grid grid-cols-3 gap-1">
              {['left', 'center', 'right'].map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => updateProp('align', a)}
                  className={`py-1.5 rounded-lg border capitalize font-semibold transition ${
                    activeElement.align === a
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Alt Text (Accessibility)</label>
            <input
              type="text"
              value={activeElement.alt || ''}
              onChange={(e) => updateProp('alt', e.target.value)}
              placeholder="Brief description of image"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Click Link URL (Optional)</label>
            <input
              type="text"
              value={activeElement.linkUrl || ''}
              onChange={(e) => updateProp('linkUrl', e.target.value)}
              placeholder="https://..."
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>
        </div>
      )}

      {/* --- BUTTON SETTINGS --- */}
      {activeElement.type === 'button' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1">Button Label</label>
            <input
              type="text"
              value={activeElement.label || ''}
              onChange={(e) => updateProp('label', e.target.value)}
              placeholder="Click Here"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Destination URL</label>
            <input
              type="text"
              value={activeElement.url || ''}
              onChange={(e) => updateProp('url', e.target.value)}
              placeholder="https://example.com"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-bold text-slate-600 mb-1">Background</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={activeElement.backgroundColor || '#2563eb'}
                  onChange={(e) => updateProp('backgroundColor', e.target.value)}
                  className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200"
                />
                <span className="text-[11px] text-slate-500 font-mono">
                  {activeElement.backgroundColor || '#2563eb'}
                </span>
              </div>
            </div>

            <div>
              <label className="block font-bold text-slate-600 mb-1">Text Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={activeElement.textColor || '#ffffff'}
                  onChange={(e) => updateProp('textColor', e.target.value)}
                  className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200"
                />
                <span className="text-[11px] text-slate-500 font-mono">
                  {activeElement.textColor || '#ffffff'}
                </span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block font-bold text-slate-600 mb-1">Border Radius</label>
              <select
                value={activeElement.borderRadius ?? 8}
                onChange={(e) => updateProp('borderRadius', Number(e.target.value))}
                className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
              >
                <option value={0}>Square (0px)</option>
                <option value={4}>Slight (4px)</option>
                <option value={8}>Rounded (8px)</option>
                <option value={16}>Curved (16px)</option>
                <option value={24}>Pill (24px)</option>
              </select>
            </div>

            <div>
              <label className="block font-bold text-slate-600 mb-1">Alignment</label>
              <select
                value={activeElement.align || 'center'}
                onChange={(e) => updateProp('align', e.target.value)}
                className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
              >
                <option value="left">Left</option>
                <option value="center">Center</option>
                <option value="right">Right</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* --- DIVIDER SETTINGS --- */}
      {activeElement.type === 'divider' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1">Line Color</label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={activeElement.color || '#e2e8f0'}
                onChange={(e) => updateProp('color', e.target.value)}
                className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200"
              />
              <span className="text-[11px] text-slate-500 font-mono">
                {activeElement.color || '#e2e8f0'}
              </span>
            </div>
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Thickness</label>
            <div className="grid grid-cols-4 gap-1">
              {[1, 2, 3, 4].map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => updateProp('thickness', t)}
                  className={`py-1.5 rounded-lg border font-semibold transition ${
                    (activeElement.thickness || 1) === t
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {t}px
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="flex justify-between font-bold text-slate-600 mb-1">
              <span>Width</span>
              <span className="text-slate-400 font-normal">{activeElement.width || 100}%</span>
            </div>
            <input
              type="range"
              min="20"
              max="100"
              step="5"
              value={activeElement.width || 100}
              onChange={(e) => updateProp('width', Number(e.target.value))}
              className="w-full accent-blue-600 cursor-pointer"
            />
          </div>
        </div>
      )}

      {/* --- SPACER SETTINGS --- */}
      {activeElement.type === 'spacer' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1.5">Preset Height</label>
            <div className="grid grid-cols-3 gap-1.5">
              {[
                { label: 'Small', val: 16 },
                { label: 'Medium', val: 32 },
                { label: 'Large', val: 48 },
              ].map((p) => (
                <button
                  key={p.val}
                  type="button"
                  onClick={() => updateProp('height', p.val)}
                  className={`py-2 rounded-xl border text-xs font-bold transition ${
                    activeElement.height === p.val
                      ? 'border-blue-600 bg-blue-50 text-blue-700'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {p.label} ({p.val}px)
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="flex justify-between font-bold text-slate-600 mb-1">
              <span>Custom Height</span>
              <span className="text-slate-400 font-normal">{activeElement.height || 24}px</span>
            </div>
            <input
              type="range"
              min="8"
              max="96"
              step="4"
              value={activeElement.height || 24}
              onChange={(e) => updateProp('height', Number(e.target.value))}
              className="w-full accent-blue-600 cursor-pointer"
            />
          </div>
        </div>
      )}

      {/* --- SIGNATURE SETTINGS --- */}
      {activeElement.type === 'signature' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1">Choose Saved Signature</label>
            <select
              value={activeElement.signatureId || ''}
              onChange={(e) => {
                const s = savedSignatures.find((x) => x.id === e.target.value);
                if (s) {
                  updateProp('signatureId', s.id);
                  updateProp('html', s.html);
                  updateProp('name', s.name);
                }
              }}
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs mb-2"
            >
              <option value="">Select a signature...</option>
              {savedSignatures.map((s) => (
                <option key={s.id} value={s.id}>{s.name} {s.is_default ? '(Default)' : ''}</option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={onOpenSignatureBuilder}
            className="w-full py-2 px-3 border border-indigo-200 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold flex items-center justify-center gap-1.5 transition"
          >
            <PenTool className="w-3.5 h-3.5" />
            <span>Create / Edit Signatures</span>
          </button>
        </div>
      )}

      {/* --- FOOTER SETTINGS --- */}
      {activeElement.type === 'footer' && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-600 mb-1">Footer Text</label>
            <textarea
              rows={3}
              value={activeElement.text || ''}
              onChange={(e) => updateProp('text', e.target.value)}
              placeholder="e.g. 123 Business Avenue, Suite 400 • © 2026 Market Intel DB"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Unsubscribe Notice</label>
            <input
              type="text"
              value={activeElement.unsubscribeText || ''}
              onChange={(e) => updateProp('unsubscribeText', e.target.value)}
              placeholder="If you'd like to opt out of future emails,"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-600 mb-1">Unsubscribe Link URL</label>
            <input
              type="text"
              value={activeElement.unsubscribeUrl || ''}
              onChange={(e) => updateProp('unsubscribeUrl', e.target.value)}
              placeholder="https://... or {{unsubscribe_url}}"
              className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
            />
          </div>
        </div>
      )}

      {/* --- COLUMNS SECTION SETTINGS --- */}
      {activeElement.type === 'columns' && !isSubElement && (
        <div className="space-y-3">
          <div>
            <label className="block font-bold text-slate-700 mb-1.5 uppercase text-[10px] tracking-wider">
              Separate / Change Columns
            </label>
            <div className="grid grid-cols-4 gap-1.5">
              {COLUMN_LAYOUTS.map((layout) => {
                const isCurrent = activeElement.layout === layout.id;
                return (
                  <button
                    key={layout.id}
                    type="button"
                    onClick={() => onChangeBlockLayout && onChangeBlockLayout(selectedBlock.id, layout.id)}
                    className={`p-2 rounded-xl border flex flex-col items-center justify-center gap-1 transition cursor-pointer ${
                      isCurrent
                        ? 'border-blue-600 bg-blue-50 text-blue-700 font-bold shadow-xs'
                        : 'border-slate-200 bg-white hover:border-slate-400 text-slate-700'
                    }`}
                    title={layout.name}
                  >
                    <div className="w-8 h-3.5 flex items-center gap-0.5">
                      {layout.boxes.map((b, i) => (
                        <div
                          key={i}
                          style={{ flex: b.flex }}
                          className={`h-full border rounded-[1px] ${
                            isCurrent ? 'border-blue-600 bg-blue-200/50' : 'border-slate-600 bg-white'
                          }`}
                        />
                      ))}
                    </div>
                    <span className="text-[10px]">{layout.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {selectedColumnId && (
            <div className="p-3 bg-blue-50/70 border border-blue-200 rounded-xl space-y-2">
              <span className="font-bold text-blue-900 block text-xs">Add Element Into Column</span>
              <div className="flex flex-wrap gap-1">
                {['text', 'image', 'button', 'row', 'divider', 'spacer'].map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => onAddElementToColumn && onAddElementToColumn(selectedBlock.id, selectedColumnId, t)}
                    className={`px-2 py-1 rounded-lg border text-[10px] font-bold capitalize transition cursor-pointer ${
                      t === 'row'
                        ? 'border-indigo-400 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200'
                        : 'border-blue-300 bg-white hover:bg-blue-100 text-blue-800'
                    }`}
                  >
                    + {t === 'row' ? 'Row Block' : t}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Option to split a single-element block into columns */}
      {!isSubElement && activeElement.type !== 'columns' && activeElement.type !== 'footer' && (
        <div className="pt-2 border-t border-slate-200">
          <label className="block font-bold text-slate-600 mb-1 text-[10px] uppercase tracking-wider">
            Split Into Columns
          </label>
          <div className="grid grid-cols-4 gap-1">
            {COLUMN_LAYOUTS.slice(1, 5).map((layout) => (
              <button
                key={layout.id}
                type="button"
                onClick={() => onChangeBlockLayout && onChangeBlockLayout(selectedBlock.id, layout.id)}
                className="p-1.5 rounded-lg border border-slate-200 hover:border-blue-400 hover:bg-blue-50 text-[10px] font-bold text-slate-700 transition cursor-pointer"
                title={`Split into ${layout.name}`}
              >
                Split {layout.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* --- BACKGROUND & BORDERS STYLING --- */}
      <div className="pt-3 border-t border-slate-200 space-y-3">
        <div className="font-bold text-slate-700 flex items-center gap-1.5">
          <Palette className="w-3.5 h-3.5 text-blue-600" />
          <span>Background & Border</span>
        </div>

        {/* If a Column is specifically selected inside a Columns block */}
        {activeColumn && (
          <div className="p-2.5 bg-blue-50/70 border border-blue-200 rounded-xl space-y-2">
            <label className="block text-[11px] font-bold text-blue-900">
              Selected Column Background Color ({Math.round(activeColumn.widthPercent)}% Column)
            </label>
            <div className="flex flex-wrap items-center gap-1.5 mb-1">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => updateColumnProp('backgroundColor', c)}
                  className="w-5 h-5 rounded-md border border-slate-300 hover:scale-110 transition flex items-center justify-center cursor-pointer shadow-2xs"
                  style={{ backgroundColor: c }}
                  title={`Column background: ${c}`}
                >
                  {activeColumn.backgroundColor === c && (
                    <Check className={`w-3 h-3 ${c === '#0f172a' ? 'text-white' : 'text-slate-800'}`} />
                  )}
                </button>
              ))}
              <button
                type="button"
                onClick={() => updateColumnProp('backgroundColor', 'transparent')}
                className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                Clear
              </button>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={activeColumn.backgroundColor && activeColumn.backgroundColor !== 'transparent' ? activeColumn.backgroundColor : '#ffffff'}
                onChange={(e) => updateColumnProp('backgroundColor', e.target.value)}
                className="w-7 h-7 rounded-lg border border-slate-200 cursor-pointer"
              />
              <span className="text-[11px] text-slate-600 font-mono">
                {activeColumn.backgroundColor || 'transparent'}
              </span>
            </div>
          </div>
        )}

        {/* Block / Element Background Controls (omit for text elements to prevent duplicate Text Box Background Color controls) */}
        {activeElement.type !== 'text' && (
          <div>
            <label className="block text-[11px] font-bold text-slate-700 mb-1">
              {isSubElement
                ? 'Element Background Color'
                : activeColumn
                ? 'Entire Block Background Color'
                : 'Block Background Color'}
            </label>
            <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => updateProp('backgroundColor', c)}
                  className="w-5 h-5 rounded-md border border-slate-300 hover:scale-110 transition flex items-center justify-center cursor-pointer shadow-2xs"
                  style={{ backgroundColor: c }}
                  title={`Block background: ${c}`}
                >
                  {activeElement.backgroundColor === c && (
                    <Check className={`w-3 h-3 ${c === '#0f172a' ? 'text-white' : 'text-slate-800'}`} />
                  )}
                </button>
              ))}
              <button
                type="button"
                onClick={() => updateProp('backgroundColor', 'transparent')}
                className="text-[10px] font-bold px-1.5 py-0.5 rounded border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                Clear
              </button>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={activeElement.backgroundColor && activeElement.backgroundColor !== 'transparent' ? activeElement.backgroundColor : '#ffffff'}
                onChange={(e) => updateProp('backgroundColor', e.target.value)}
                className="w-7 h-7 rounded-lg border border-slate-200 cursor-pointer"
              />
              <span className="text-[11px] text-slate-500 font-mono">
                {activeElement.backgroundColor || 'transparent'}
              </span>
            </div>
          </div>
        )}

        {/* Border Controls */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-[11px] font-semibold text-slate-600">Border</label>
            <input
              type="checkbox"
              checked={!!activeElement.border?.enabled}
              onChange={(e) => updateBorder('enabled', e.target.checked)}
              className="rounded accent-blue-600 cursor-pointer"
            />
          </div>

          {activeElement.border?.enabled && (
            <div className="p-2 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500">Color:</span>
                <input
                  type="color"
                  value={activeElement.border?.color || '#e2e8f0'}
                  onChange={(e) => updateBorder('color', e.target.value)}
                  className="w-6 h-6 rounded cursor-pointer border border-slate-300"
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-slate-500">Width:</span>
                <select
                  value={activeElement.border?.width || 1}
                  onChange={(e) => updateBorder('width', Number(e.target.value))}
                  className="p-1 border border-slate-200 rounded-lg text-xs bg-white"
                >
                  <option value={1}>1px</option>
                  <option value={2}>2px</option>
                  <option value={3}>3px</option>
                </select>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PropertiesPanel;
