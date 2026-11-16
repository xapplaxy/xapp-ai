export type Translate = (key: string, params?: Record<string, string | number>) => string;

type Dict = Record<string, unknown>;

/** Supported languages; the first is the default and the fallback. Set by the create-xapp scaffold. */
export const LANGUAGES: readonly string[] = __LANGUAGES__;
const FALLBACK_LOCALE = LANGUAGES[0];

let dict = $state<Dict>({});
let fallback = $state<Dict>({});
let active = $state<string>(FALLBACK_LOCALE);

function lookup(source: Dict, key: string): string | undefined {
	let node: unknown = source;
	for (const part of key.split('.')) {
		if (node === null || typeof node !== 'object') return undefined;
		node = (node as Dict)[part];
	}
	return typeof node === 'string' ? node : undefined;
}

/** Translate a dotted key, replacing `{name}` placeholders. Falls back to the default language, then the key. */
export const t: Translate = (key, params) => {
	const text = lookup(dict, key) ?? lookup(fallback, key) ?? key;
	return params
		? text.replace(/\{(\w+)\}/g, (m, name) => (name in params ? String(params[name]) : m))
		: text;
};

async function fetchLocale(appId: string, locale: string): Promise<Dict | null> {
	try {
		const res = await fetch(`/cdn/miniapps/${appId}/locale/${locale}/i18n.json`);
		return res.status === 200 ? ((await res.json()) as Dict) : null;
	} catch {
		return null;
	}
}

/** Maps the page language (<html lang>) to a supported language: exact match, then base language, then default. */
function resolveLanguage(): string {
	const raw = (typeof document !== 'undefined' ? document.documentElement.lang : '').trim();
	if (!raw) return FALLBACK_LOCALE;
	const lower = raw.toLowerCase();
	const base = lower.split('-')[0];
	return (
		LANGUAGES.find((l) => l.toLowerCase() === lower) ??
		LANGUAGES.find((l) => l.toLowerCase() === base) ??
		LANGUAGES.find((l) => l.toLowerCase().split('-')[0] === base) ??
		FALLBACK_LOCALE
	);
}

/** The active supported language code (after loadI18n). */
export function getLang(): string {
	return active;
}

/** BCP 47 locale for Intl number/date formatting, from the page language (<html lang>). */
export function getLocale(): string {
	const lang = typeof document !== 'undefined' ? document.documentElement.lang : '';
	return lang || FALLBACK_LOCALE;
}

/** Loads the translations for the page language (<html lang>), with the default language as fallback. */
export async function loadI18n(appId: string): Promise<void> {
	const locale = resolveLanguage();
	const [fb, current] = await Promise.all([
		fetchLocale(appId, FALLBACK_LOCALE),
		locale === FALLBACK_LOCALE ? Promise.resolve(null) : fetchLocale(appId, locale)
	]);
	active = current ? locale : FALLBACK_LOCALE;
	fallback = fb ?? {};
	dict = current ?? fb ?? {};
}
