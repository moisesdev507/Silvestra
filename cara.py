import math
import random
import time
import tkinter as tk
from tkinter import messagebox, simpledialog

import acciones
from config import (
    COLOR_CUERPO,
    COLOR_DORMIDA,
    COLOR_ESCUCHA,
    COLOR_VIVA,
    TRANSPARENTE,
)


class Cara:
    """El rostro flotante: dibujo, parpadeo, boca, burbuja de texto y menú."""

    # Ajustes del paseo (en segundos)
    IDLE_PASEO = 6          # cuánto espera sin que la toques antes de pasearse sola
    PRIMERA_PAUSA = (2, 5)
    PAUSA = (4, 12)         # descanso entre paseos
    PAUSA_ORDEN = (1, 3)    # descanso cuando se lo pides por voz

    def __init__(self, al_escribir, al_conversar, al_renacer, al_descansar):
        self.hablando = False
        self.burbuja = None
        self.ventana_entrada = None
        self.viva = False
        self.escuchando = False
        self.dx = 0
        self.dy = 0
        # Paseo por la pantalla
        self.mx = 0
        self.my = 0
        self.destino = None
        self.sincronizar = True
        self.ultima_interaccion = time.time()
        self.pausa_hasta = time.time() + 10
        self.fx = 0.0
        self.fy = 0.0
        self.paseo_hasta = 0.0
        self.forzado_destino = False
        self.seguir_hasta = 0.0
        self.baile_hasta = 0.0

        self.root = tk.Tk()
        self.root.title("Silvestra")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.config(bg=TRANSPARENTE)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENTE)
        except tk.TclError:
            pass

        tam = 180
        self.canvas = tk.Canvas(
            self.root, width=tam, height=tam, bg=TRANSPARENTE, highlightthickness=0
        )
        self.canvas.pack()
        ancho = self.root.winfo_screenwidth()
        alto = self.root.winfo_screenheight()
        self.root.geometry(f"{tam}x{tam}+{ancho - tam - 40}+{alto - tam - 100}")

        self._dibujar()

        self.canvas.bind("<ButtonPress-1>", self._inicio_arrastre)
        self.canvas.bind("<B1-Motion>", self._arrastrar)
        self.canvas.bind("<Double-Button-1>", lambda e: al_escribir())
        self.canvas.bind("<Button-3>", self._mostrar_menu)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Escribirle", command=al_escribir)
        self.menu.add_command(label="Conversar con voz (activar/desactivar)", command=al_conversar)
        self.var_paseo = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(
            label="Pasearse por la pantalla", variable=self.var_paseo, command=self._tocar
        )
        self.menu.add_command(label="Descansar (desaparece hasta que la llames)", command=al_descansar)
        self.menu.add_command(label="Renacer (borrar su memoria)", command=al_renacer)
        self.menu.add_separator()
        self.menu.add_command(label="Salir", command=self.root.destroy)

        self.root.after(3000, self._parpadear)
        self.root.after(200, self._animar_boca)
        self.root.after(1000, self._mover)
        self.root.after(2500, self._mirar)

        # Cosas que se le pueden pedir por voz
        acciones.registrar("pasear", self.pasear_ahora, "se pasea por toda la pantalla un buen rato (úsala si te piden pasearte, moverte o caminar)")
        acciones.registrar("quedarse_quieta", self.quedarse_quieta, "se queda quieta en su lugar y deja de pasearse")
        acciones.registrar("ir_esquina_derecha", lambda: self.ir_a("derecha"), "va a la esquina inferior derecha")
        acciones.registrar("ir_esquina_izquierda", lambda: self.ir_a("izquierda"), "va a la esquina inferior izquierda")
        acciones.registrar("ir_centro", lambda: self.ir_a("centro"), "va al centro de la pantalla")
        acciones.registrar("seguir_mouse", self.seguir_mouse, "sigue el cursor del mouse un rato (úsala si te piden que te siga)")
        acciones.registrar("bailar", self.bailar, "baila unos segundos")

    # ---------- Dibujo ----------
    def _dibujar(self):
        c = self.canvas
        self.cuerpo = c.create_oval(10, 10, 170, 170, fill=COLOR_CUERPO, outline=COLOR_DORMIDA, width=4)
        self.ojo_i = c.create_oval(55, 60, 80, 95, fill=COLOR_DORMIDA, outline="")
        self.ojo_d = c.create_oval(100, 60, 125, 95, fill=COLOR_DORMIDA, outline="")
        self.boca_linea = c.create_line(65, 125, 115, 125, width=5, fill=COLOR_DORMIDA, capstyle=tk.ROUND)
        self.boca_abierta = c.create_oval(75, 115, 105, 140, fill=COLOR_DORMIDA, outline="", state="hidden")

    def _pintar(self):
        color = COLOR_VIVA if self.viva else COLOR_DORMIDA
        c = self.canvas
        c.itemconfigure(self.cuerpo, outline=COLOR_ESCUCHA if self.escuchando else color)
        for item in (self.ojo_i, self.ojo_d, self.boca_linea, self.boca_abierta):
            c.itemconfigure(item, fill=color)

    def poner_viva(self, viva):
        self.viva = viva
        self._pintar()

    def poner_escuchando(self, escuchando):
        self.escuchando = escuchando
        self._pintar()

    def _pos_ojos(self, abiertos=True):
        x, y = self.mx, self.my
        if abiertos:
            self.canvas.coords(self.ojo_i, 55 + x, 60 + y, 80 + x, 95 + y)
            self.canvas.coords(self.ojo_d, 100 + x, 60 + y, 125 + x, 95 + y)
        else:
            self.canvas.coords(self.ojo_i, 55 + x, 76 + y, 80 + x, 80 + y)
            self.canvas.coords(self.ojo_d, 100 + x, 76 + y, 125 + x, 80 + y)

    def _parpadear(self):
        self._pos_ojos(False)
        self.root.after(150, self._abrir_ojos)
        self.root.after(random.randint(2500, 5500), self._parpadear)

    def _abrir_ojos(self):
        self._pos_ojos(True)

    def _mirar(self):
        # Mueve los ojos de vez en cuando, como si mirara alrededor.
        if self.hablando or self.escuchando or self.destino is not None:
            if self.destino is None and (self.mx or self.my):
                self.mx = self.my = 0
                self._pos_ojos()
        else:
            self.mx = random.choice([-6, 0, 0, 6])
            self.my = random.choice([-3, 0, 0, 3])
            self._pos_ojos()
        self.root.after(random.randint(1500, 4000), self._mirar)

    # ---------- Paseo ----------
    def _tocar(self):
        """El usuario tomó el control: se cancelan las órdenes de movimiento."""
        self.ultima_interaccion = time.time()
        self.destino = None
        self.forzado_destino = False
        self.paseo_hasta = 0.0
        self.seguir_hasta = 0.0
        self.baile_hasta = 0.0

    # Órdenes (también se activan por voz)
    def pasear_ahora(self, segundos=180):
        self._tocar()
        self.var_paseo.set(True)
        self.paseo_hasta = time.time() + segundos
        self.pausa_hasta = 0.0
        self.sincronizar = True

    def quedarse_quieta(self):
        self._tocar()
        self.var_paseo.set(False)

    def ir_a(self, lugar):
        self._tocar()
        ancho = self.root.winfo_screenwidth()
        alto = self.root.winfo_screenheight()
        tam = 180
        puntos = {
            "derecha": (ancho - tam - 40, alto - tam - 100),
            "izquierda": (40, alto - tam - 100),
            "centro": ((ancho - tam) // 2, (alto - tam) // 2),
        }
        self.destino = puntos[lugar]
        self.forzado_destino = True
        self.sincronizar = True

    def seguir_mouse(self, segundos=90):
        self._tocar()
        self.seguir_hasta = time.time() + segundos
        self.sincronizar = True

    def bailar(self, segundos=4):
        self._tocar()
        self.baile_hasta = time.time() + segundos
        self.sincronizar = True

    def _activo(self):
        ahora = time.time()
        return (
            (self.forzado_destino and self.destino is not None)
            or ahora < self.paseo_hasta
            or ahora < self.seguir_hasta
            or ahora < self.baile_hasta
        )

    def _puede_mover(self):
        base = self.viva and self.ventana_entrada is None and self.root.state() != "withdrawn"
        if not base:
            return False
        if self._activo():
            return True
        return (
            self.var_paseo.get()
            and not self.hablando
            and not self.escuchando
            and self.burbuja is None
            and time.time() - self.ultima_interaccion > self.IDLE_PASEO
        )

    def _elegir_destino(self):
        ancho = self.root.winfo_screenwidth()
        alto = self.root.winfo_screenheight()
        tam = 180
        for _ in range(6):
            x = random.randint(0, max(0, ancho - tam))
            y = random.randint(int(alto * 0.25), max(int(alto * 0.25), alto - tam - 70))
            if abs(x - self.fx) + abs(y - self.fy) > 200:
                break
        self.destino = (x, y)

    def _poner(self, x, y):
        self.root.geometry(f"+{int(x)}+{int(y)}")
        self._colocar_burbuja()

    def _mover(self):
        ahora = time.time()
        if not self._puede_mover():
            self.destino = None
            self.sincronizar = True
            self.root.after(300, self._mover)
            return
        if self.sincronizar:
            self.fx = float(self.root.winfo_x())
            self.fy = float(self.root.winfo_y())
            self.sincronizar = False
            if ahora < self.paseo_hasta:
                self.pausa_hasta = 0.0
            else:
                self.pausa_hasta = ahora + random.uniform(*self.PRIMERA_PAUSA)

        # Baile
        if ahora < self.baile_hasta:
            fase = math.sin(ahora * 9)
            self._poner(self.fx + 25 * fase, self.fy - 10 * abs(fase))
            self.root.after(30, self._mover)
            return
        if self.baile_hasta:
            self.baile_hasta = 0.0
            self._poner(self.fx, self.fy)

        ancho = self.root.winfo_screenwidth()
        alto = self.root.winfo_screenheight()

        # Seguir al mouse
        if ahora < self.seguir_hasta:
            tx = min(max(self.root.winfo_pointerx() + 40, 0), ancho - 180)
            ty = min(max(self.root.winfo_pointery() + 40, 0), alto - 250)
            dx, dy = tx - self.fx, ty - self.fy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > 60:
                paso = max(3.0, dist * 0.08)
                self.fx += dx / dist * paso
                self.fy += dy / dist * paso
                self.mx = 5 if dx > 0 else -5
                self._poner(self.fx, self.fy)
            else:
                self.mx = 0
            self._pos_ojos()
            self.root.after(30, self._mover)
            return
        self.seguir_hasta = 0.0

        # Paseo o ida a un lugar
        if self.destino is None:
            if ahora < self.pausa_hasta:
                self.root.after(200, self._mover)
                return
            self._elegir_destino()
        dx = self.destino[0] - self.fx
        dy = self.destino[1] - self.fy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 2:
            self.destino = None
            self.forzado_destino = False
            self.mx = self.my = 0
            self._pos_ojos()
            pausa = self.PAUSA_ORDEN if ahora < self.paseo_hasta else self.PAUSA
            self.pausa_hasta = ahora + random.uniform(*pausa)
            self.root.after(200, self._mover)
            return
        paso = min(dist, max(2.5, dist * 0.06))
        self.fx += dx / dist * paso
        self.fy += dy / dist * paso
        self.mx = 5 if dx > 0 else -5
        self.my = 0
        self._poner(self.fx, self.fy)
        self._pos_ojos()
        self.root.after(30, self._mover)

    def _animar_boca(self):
        c = self.canvas
        if self.hablando:
            abierta = c.itemcget(self.boca_abierta, "state") == "normal"
            c.itemconfigure(self.boca_abierta, state="hidden" if abierta else "normal")
            c.itemconfigure(self.boca_linea, state="normal" if abierta else "hidden")
        else:
            c.itemconfigure(self.boca_abierta, state="hidden")
            c.itemconfigure(self.boca_linea, state="normal")
        self.root.after(160, self._animar_boca)

    # ---------- Ratón ----------
    def _inicio_arrastre(self, e):
        self.dx, self.dy = e.x, e.y
        self._tocar()

    def _arrastrar(self, e):
        x = self.root.winfo_x() + e.x - self.dx
        y = self.root.winfo_y() + e.y - self.dy
        self.root.geometry(f"+{x}+{y}")
        self.ultima_interaccion = time.time()

    def _mostrar_menu(self, e):
        self._tocar()
        self.menu.tk_popup(e.x_root, e.y_root)

    # ---------- Burbuja ----------
    def decir(self, texto, ms=None):
        self.ultima_interaccion = time.time()
        if ms is None:
            ms = max(3000, len(texto) * 80)
        if self.burbuja is not None:
            self.burbuja.destroy()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        tk.Label(
            b, text=texto, wraplength=280, justify="left", bg=COLOR_CUERPO,
            fg="white", font=("Segoe UI", 11), padx=14, pady=10,
        ).pack()
        self.burbuja = b
        self._colocar_burbuja()
        self.hablando = True
        self.root.after(ms, lambda: self._cerrar_burbuja(b))

    def _colocar_burbuja(self):
        b = self.burbuja
        if b is None:
            return
        b.update_idletasks()
        x = max(10, self.root.winfo_rootx() - b.winfo_reqwidth() + 30)
        y = max(10, self.root.winfo_rooty() - b.winfo_reqheight() + 50)
        b.geometry(f"+{x}+{y}")

    def _cerrar_burbuja(self, b):
        if self.burbuja is b:
            b.destroy()
            self.burbuja = None
            self.hablando = False

    # ---------- Diálogos ----------
    def preguntar(self, titulo, texto):
        return simpledialog.askstring(titulo, texto, parent=self.root)

    def confirmar(self, titulo, texto):
        return messagebox.askyesno(titulo, texto, parent=self.root)

    def abrir_entrada(self, titulo, al_enviar):
        self._tocar()
        if self.ventana_entrada is not None:
            self.ventana_entrada.focus_force()
            return
        v = tk.Toplevel(self.root)
        v.title(titulo)
        v.attributes("-topmost", True)
        entrada = tk.Entry(v, width=60, font=("Segoe UI", 12))
        entrada.pack(padx=12, pady=12)
        entrada.focus_force()

        def cerrar(_e=None):
            if self.ventana_entrada is not None:
                self.ventana_entrada.destroy()
                self.ventana_entrada = None

        def enviar(_e=None):
            texto = entrada.get().strip()
            cerrar()
            if texto:
                al_enviar(texto)

        entrada.bind("<Return>", enviar)
        entrada.bind("<Escape>", cerrar)
        v.protocol("WM_DELETE_WINDOW", cerrar)
        self.ventana_entrada = v

    def ocultar(self):
        if self.burbuja is not None:
            self.burbuja.destroy()
            self.burbuja = None
        self.hablando = False
        self.root.withdraw()

    def mostrar(self):
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    def iniciar(self):
        self.root.mainloop()