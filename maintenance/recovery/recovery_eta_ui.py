"""Read-only recovery ETA bridge; normal printing keeps its original estimator."""
import time


def adjusted_total(panel, original, elapsed):
    now = time.monotonic()
    if now >= getattr(panel, '_recovery_eta_next', 0):
        panel._recovery_eta_next = now + 5
        def received(reply, *args):
            status = reply.get('result', {}).get('status', {})
            panel._recovery_eta = status.get('lugo_recovery', {}).get('eta')
            panel._recovery_eta_received = time.monotonic()
        panel._screen._ws.send_method('printer.objects.query',
            {'objects': {'lugo_recovery': None}}, received)
    eta = getattr(panel, '_recovery_eta', None)
    if (not eta or eta.get('filename') != panel.filename or not eta.get('active')
            or now-getattr(panel,'_recovery_eta_received',0)>15):
        return original
    remaining = eta.get('remaining')
    if remaining is None: return 0.
    # Updates every five seconds, with a countdown between updates.
    return elapsed + max(0., remaining-max(0.,elapsed-eta.get('elapsed',elapsed)))
