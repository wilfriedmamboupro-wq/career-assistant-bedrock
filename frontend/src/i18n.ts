export type Lang = 'fr' | 'en'

export const strings = {
  fr: {
    open: 'Ouvrir l’assistant carrière',
    close: 'Fermer',
    reset: 'Nouvelle conversation',
    title: 'Career Assistant',
    badge: 'Prototype personnel — non affilié à l’entreprise',
    welcome:
      'Bonjour ! Je réponds aux questions sur les carrières à partir du contenu public du site carrières, et je peux chercher des offres. Posez votre question en français ou en anglais.',
    suggestions: [
      'Est-ce que le télétravail est possible ?',
      'Quelles offres en données à Montréal ?',
      'Comment se passe le processus d’embauche ?',
    ],
    placeholder: 'Votre question…',
    send: 'Envoyer',
    sources: 'Sources',
    jobs: 'Offres trouvées',
    viewJob: 'Voir l’offre',
    masked: 'Des renseignements personnels ont été masqués avant le traitement.',
    recruiter: 'Parler à un recruteur',
    recruiterDone: 'Demande envoyée',
    disclaimer:
      'Je peux me tromper : vérifiez toujours sur le site officiel. Ne partagez pas de renseignements personnels.',
    error: 'Le service ne répond pas. Réessayez dans un instant.',
    thinking: 'L’assistant écrit…',
    langSwitch: 'EN',
    langLabel: 'Switch to English',
    jobLang: { fr: 'Français', en: 'Anglais', bilingual: 'Bilingue' },
  },
  en: {
    open: 'Open the career assistant',
    close: 'Close',
    reset: 'New conversation',
    title: 'Career Assistant',
    badge: 'Personal prototype — not affiliated with the company',
    welcome:
      'Hi! I answer career questions from the public careers website and can search job openings. Ask in English or French.',
    suggestions: [
      'Is remote work possible?',
      'Any data jobs in Toronto?',
      'What does the hiring process look like?',
    ],
    placeholder: 'Your question…',
    send: 'Send',
    sources: 'Sources',
    jobs: 'Matching jobs',
    viewJob: 'View posting',
    masked: 'Personal information was masked before processing.',
    recruiter: 'Talk to a recruiter',
    recruiterDone: 'Request sent',
    disclaimer:
      'I can make mistakes: always check the official website. Do not share personal information.',
    error: 'The service is not responding. Please try again shortly.',
    thinking: 'The assistant is typing…',
    langSwitch: 'FR',
    langLabel: 'Passer en français',
    jobLang: { fr: 'French', en: 'English', bilingual: 'Bilingual' },
  },
} as const

export type Strings = (typeof strings)[Lang]
