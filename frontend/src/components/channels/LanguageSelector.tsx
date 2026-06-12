const LANGUAGES = [
  { code: 'pt', name: 'Portugues', flag: '\u{1F1E7}\u{1F1F7}' },
  { code: 'es', name: 'Espanol', flag: '\u{1F1EA}\u{1F1F8}' },
  { code: 'en', name: 'English', flag: '\u{1F1FA}\u{1F1F8}' },
  { code: 'fr', name: 'Francais', flag: '\u{1F1EB}\u{1F1F7}' },
  { code: 'it', name: 'Italiano', flag: '\u{1F1EE}\u{1F1F9}' },
  { code: 'de', name: 'Deutsch', flag: '\u{1F1E9}\u{1F1EA}' },
  { code: 'ja', name: '日本語', flag: '\u{1F1EF}\u{1F1F5}' },
  { code: 'ko', name: '한국어', flag: '\u{1F1F0}\u{1F1F7}' },
  { code: 'zh', name: '中文', flag: '\u{1F1E8}\u{1F1F3}' },
  { code: 'ar', name: 'العربية', flag: '\u{1F1F8}\u{1F1E6}' },
  { code: 'hi', name: 'हिन्दी', flag: '\u{1F1EE}\u{1F1F3}' },
  { code: 'ru', name: 'Русский', flag: '\u{1F1F7}\u{1F1FA}' },
  { code: 'tr', name: 'Turkce', flag: '\u{1F1F9}\u{1F1F7}' },
  { code: 'nl', name: 'Nederlands', flag: '\u{1F1F3}\u{1F1F1}' },
  { code: 'pl', name: 'Polski', flag: '\u{1F1F5}\u{1F1F1}' },
  { code: 'sv', name: 'Svenska', flag: '\u{1F1F8}\u{1F1EA}' },
]

interface LanguageSelectorProps {
  value: string
  onChange: (code: string) => void
  compact?: boolean
}

export default function LanguageSelector({
  value,
  onChange,
  compact = false,
}: LanguageSelectorProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-gray-800 border border-gray-700 rounded-md px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
    >
      <option value="">Select language...</option>
      {LANGUAGES.map((lang) => (
        <option key={lang.code} value={lang.code}>
          {lang.flag} {compact ? lang.code.toUpperCase() : lang.name}
        </option>
      ))}
    </select>
  )
}

export { LANGUAGES }
