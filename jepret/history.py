"""Undo/redo sederhana berbasis snapshot dokumen."""


class History:
    def __init__(self, limit=200):
        self._undo = []
        self._redo = []
        self._limit = limit
        self.on_change = None

    def push(self, snapshot):
        self._undo.append(snapshot)
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()
        self._notify()

    def undo(self, current):
        if not self._undo:
            return None
        self._redo.append(current)
        state = self._undo.pop()
        self._notify()
        return state

    def redo(self, current):
        if not self._redo:
            return None
        self._undo.append(current)
        state = self._redo.pop()
        self._notify()
        return state

    def clear(self):
        self._undo.clear()
        self._redo.clear()
        self._notify()

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def _notify(self):
        if self.on_change:
            self.on_change()
