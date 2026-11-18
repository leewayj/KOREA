import { useEffect, useRef } from 'react'
import { Button } from './Button'
import './SeatPage.css'
import './return-dialog.css'

export default function ReturnSeatDialog({ triggerRef, onOpenChange, onConfirm, saving }) {
  const dialog = useRef(null)

  useEffect(() => {
    const panel = dialog.current
    const trigger = triggerRef.current
    const buttons = panel.querySelectorAll('button')
    buttons[0].focus({ preventScroll: true })
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !saving) { event.preventDefault(); onOpenChange(false) }
      if (event.key !== 'Tab') return
      const first = buttons[0], last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus({ preventScroll: true }) }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus({ preventScroll: true }) }
    }
    panel.addEventListener('keydown', onKeyDown)
    return () => {
      panel.removeEventListener('keydown', onKeyDown)
      if (trigger?.isConnected) trigger.focus({ preventScroll: true })
    }
  }, [onOpenChange, triggerRef, saving])

  return <>
    <div className="seat-modal-backdrop" aria-hidden="true" onClick={() => { if (!saving) onOpenChange(false) }} />
    <section ref={dialog} className="seat-dialog return-dialog" role="dialog" aria-modal="true" aria-labelledby="return-dialog-title" aria-describedby="return-dialog-description">
      <h2 id="return-dialog-title">좌석을 반납하시겠습니까?</h2>
      <p id="return-dialog-description">확인하면 좌석이 반납되고<br />홈 화면으로 이동합니다.</p>
      <div className="seat-dialog-actions">
        <Button isDisabled={saving} variant="neutral" onPress={() => onOpenChange(false)}>취소</Button>
        <Button isDisabled={saving} onPress={onConfirm}>확인</Button>
      </div>
    </section>
  </>
}
