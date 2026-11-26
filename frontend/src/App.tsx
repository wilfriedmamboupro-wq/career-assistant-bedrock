import { ChatWidget } from './components/ChatWidget'

export default function App() {
  return (
    <main className="host">
      <h1>Career Assistant</h1>
      <p className="lead">
        Démo d’un assistant carrière bilingue (FR/EN) : réponses sourcées à partir de contenu
        carrières public, recherche d’offres par outil, garde-fous sur les renseignements
        personnels.
      </p>
      <p className="lead muted">
        Prototype personnel, non affilié à l’entreprise dont le contenu public sert d’exemple.
        L’assistant informe et oriente ; il ne présélectionne ni n’évalue aucun candidat.
      </p>
      <ChatWidget defaultOpen />
    </main>
  )
}
