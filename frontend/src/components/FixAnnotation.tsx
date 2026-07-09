import { useState } from 'react'
import { addFixNote } from '../api/client'

interface FixAnnotationProps {
  sessionId: string
  existingNote: string | null
}

export default function FixAnnotation({ sessionId, existingNote }: FixAnnotationProps) {
  const [prevSessionId, setPrevSessionId] = useState(sessionId)
  const [prevExistingNote, setPrevExistingNote] = useState(existingNote)
  const [savedNote, setSavedNote] = useState(existingNote || '')
  const [note, setNote] = useState(existingNote || '')
  const [isSaving, setIsSaving] = useState(false)
  const [isEditing, setIsEditing] = useState(!existingNote)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Reset the editor when the session or its existing note changes. Adjusting
  // state during render (guarded by the previous prop values) is the
  // React-recommended pattern for prop-driven resets and avoids the cascading
  // render that a synchronous setState in an effect would trigger.
  if (sessionId !== prevSessionId || existingNote !== prevExistingNote) {
    setPrevSessionId(sessionId)
    setPrevExistingNote(existingNote)
    const nextNote = existingNote || ''
    setSavedNote(nextNote)
    setNote(nextNote)
    setIsEditing(!nextNote)
    setSaveError(null)
  }

  const handleSave = async () => {
    const trimmedNote = note.trim()
    if (!trimmedNote) return
    setIsSaving(true)
    setSaveError(null)
    try {
      await addFixNote(sessionId, trimmedNote)
      setSavedNote(trimmedNote)
      setNote(trimmedNote)
      setIsEditing(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save fix note'
      setSaveError(message)
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancel = () => {
    setNote(savedNote)
    setIsEditing(false)
    setSaveError(null)
  }

  if (!isEditing && savedNote) {
    return (
      <div className="fix-annotation">
        <span className="fix-label">Fix:</span>
        <span className="fix-text">{savedNote}</span>
        <button className="fix-edit-btn" onClick={() => setIsEditing(true)} aria-label="Edit fix note">Edit</button>
      </div>
    )
  }

  return (
    <div className="fix-annotation">
      <input
        type="text"
        className="fix-input"
        placeholder="How did you fix this?"
        value={note}
        onChange={e => setNote(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') handleSave() }}
      />
      <button className="fix-save-btn" onClick={handleSave} disabled={isSaving || !note.trim()}>
        {isSaving ? 'Saving...' : 'Save'}
      </button>
      {savedNote && (
        <button className="fix-cancel-btn" onClick={handleCancel}>
          Cancel
        </button>
      )}
      {saveError && <span className="fix-error">{saveError}</span>}
    </div>
  )
}
