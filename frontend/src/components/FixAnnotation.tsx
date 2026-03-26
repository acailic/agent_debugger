import { useState } from 'react'
import { addFixNote } from '../api/client'

interface FixAnnotationProps {
  sessionId: string
  existingNote: string | null
}

export default function FixAnnotation({ sessionId, existingNote }: FixAnnotationProps) {
  const [note, setNote] = useState(existingNote || '')
  const [isSaving, setIsSaving] = useState(false)
  const [isEditing, setIsEditing] = useState(!existingNote)

  const handleSave = async () => {
    if (!note.trim()) return
    setIsSaving(true)
    try {
      await addFixNote(sessionId, note.trim())
      setIsEditing(false)
    } catch {
      // Silently fail — fix notes are optional
    } finally {
      setIsSaving(false)
    }
  }

  if (!isEditing && existingNote) {
    return (
      <div className="fix-annotation">
        <span className="fix-label">Fix:</span>
        <span className="fix-text">{existingNote}</span>
        <button className="fix-edit-btn" onClick={() => setIsEditing(true)}>Edit</button>
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
      {existingNote && (
        <button className="fix-cancel-btn" onClick={() => { setNote(existingNote); setIsEditing(false) }}>
          Cancel
        </button>
      )}
    </div>
  )
}
