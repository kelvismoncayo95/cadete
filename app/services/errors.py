class ErrorDeNegocio(Exception):
    """Una regla del negocio no se cumple. La API la convierte en una respuesta con ese código."""

    def __init__(self, status_code: int, detalle: str):
        self.status_code = status_code
        self.detalle = detalle
        super().__init__(detalle)
