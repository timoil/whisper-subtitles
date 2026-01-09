/**
 * Internationalization (i18n) module for Whisper Subtitles
 * Loads translations from YAML files and provides translation functions
 */

const i18n = {
    currentLocale: 'en',
    translations: {},
    supportedLocales: ['ru', 'en', 'uk', 'kk', 'de', 'fr', 'es', 'it', 'pt', 'ja', 'zh', 'ko', 'tr', 'ar', 'hi'],
    defaultLocale: 'en',

    /**
     * Initialize i18n system
     * Detects browser language and loads appropriate translations
     */
    async init() {
        // Get saved locale or detect from browser
        const savedLocale = localStorage.getItem('interfaceLanguage');
        const browserLocale = this.detectBrowserLanguage();

        this.currentLocale = savedLocale || browserLocale;

        // Load translations
        await this.loadTranslations(this.currentLocale);

        console.log(`[i18n] Initialized with locale: ${this.currentLocale}`);
    },

    /**
     * Detect browser language and map to supported locale
     */
    detectBrowserLanguage() {
        const browserLang = navigator.language || navigator.userLanguage;
        const langCode = browserLang.split('-')[0].toLowerCase();

        if (this.supportedLocales.includes(langCode)) {
            return langCode;
        }

        return this.defaultLocale;
    },

    /**
     * Load translations from YAML file
     */
    async loadTranslations(locale) {
        try {
            const response = await fetch(`/static/locales/${locale}.yml`);
            if (!response.ok) {
                throw new Error(`Failed to load ${locale} translations`);
            }

            const yamlText = await response.text();
            this.translations = this.parseYaml(yamlText);
            this.currentLocale = locale;

        } catch (error) {
            console.warn(`[i18n] Failed to load ${locale}, falling back to ${this.defaultLocale}`);

            if (locale !== this.defaultLocale) {
                await this.loadTranslations(this.defaultLocale);
            }
        }
    },

    /**
     * Simple YAML parser for flat/nested key-value pairs
     */
    parseYaml(yamlText) {
        const result = {};
        const lines = yamlText.split('\n');
        const stack = [{ indent: -1, obj: result }];

        for (const line of lines) {
            // Skip empty lines and comments
            if (!line.trim() || line.trim().startsWith('#')) continue;

            const indent = line.search(/\S/);
            const content = line.trim();

            // Parse key: value or key:
            const colonIndex = content.indexOf(':');
            if (colonIndex === -1) continue;

            const key = content.substring(0, colonIndex).trim();
            let value = content.substring(colonIndex + 1).trim();

            // Remove quotes from value
            if ((value.startsWith('"') && value.endsWith('"')) ||
                (value.startsWith("'") && value.endsWith("'"))) {
                value = value.slice(1, -1);
            }

            // Pop stack to find parent
            while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
                stack.pop();
            }

            const parent = stack[stack.length - 1].obj;

            if (value === '') {
                // Nested object
                parent[key] = {};
                stack.push({ indent, obj: parent[key] });
            } else {
                // Leaf value
                parent[key] = value;
            }
        }

        return result;
    },

    /**
     * Get translation by dot-notation key
     * @param {string} key - Translation key like 'settings.title'
     * @param {object} params - Optional parameters for interpolation
     * @returns {string} Translated string or key if not found
     */
    t(key, params = {}) {
        const keys = key.split('.');
        let value = this.translations;

        for (const k of keys) {
            if (value && typeof value === 'object' && k in value) {
                value = value[k];
            } else {
                console.warn(`[i18n] Missing translation: ${key}`);
                return key;
            }
        }

        if (typeof value !== 'string') {
            return key;
        }

        // Simple parameter interpolation {param}
        return value.replace(/\{(\w+)\}/g, (match, param) => {
            return params[param] !== undefined ? params[param] : match;
        });
    },

    /**
     * Change locale and reload translations
     */
    async setLocale(locale) {
        if (!this.supportedLocales.includes(locale)) {
            console.warn(`[i18n] Unsupported locale: ${locale}`);
            return false;
        }

        await this.loadTranslations(locale);
        localStorage.setItem('interfaceLanguage', locale);

        // Apply translations to DOM
        this.applyTranslations();

        // Dispatch event for UI update
        window.dispatchEvent(new CustomEvent('localeChanged', { detail: { locale } }));

        return true;
    },

    /**
     * Apply translations to all elements with data-i18n attribute
     */
    applyTranslations() {
        const elements = document.querySelectorAll('[data-i18n]');

        for (const el of elements) {
            const key = el.getAttribute('data-i18n');
            const translated = this.t(key);

            // Don't replace if translation not found (returns key)
            if (translated !== key) {
                el.textContent = translated;
            }
        }

        console.log(`[i18n] Applied translations to ${elements.length} elements`);
    },

    /**
     * Get list of supported locales with their native names
     */
    getLocales() {
        return [
            { code: 'ru', name: 'Русский' },
            { code: 'en', name: 'English' },
            { code: 'uk', name: 'Українська' },
            { code: 'kk', name: 'Қазақша' },
            { code: 'de', name: 'Deutsch' },
            { code: 'fr', name: 'Français' },
            { code: 'es', name: 'Español' },
            { code: 'it', name: 'Italiano' },
            { code: 'pt', name: 'Português' },
            { code: 'ja', name: '日本語' },
            { code: 'zh', name: '中文' },
            { code: 'ko', name: '한국어' },
            { code: 'tr', name: 'Türkçe' },
            { code: 'ar', name: 'العربية' },
            { code: 'hi', name: 'हिन्दी' }
        ];
    }
};

// Export for use in app.js
window.i18n = i18n;
