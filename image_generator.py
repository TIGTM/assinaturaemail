"""
image_generator.py — Gerador de imagens de assinatura
Recebe a imagem base, o layout JSON (campos + posições) e os dados do
funcionário, e renderiza uma imagem PNG personalizada usando Pillow.
"""
import os
import re
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


# Mapeamento de campo -> chave no dicionário do funcionário
FIELD_KEYS = {
    "name":       "name",
    "title":      "title",
    "phone":      "phone",
    "email":      "email",
    "department": "department",
    "website":    "website",
    "instagram":  "instagram",
    "extra1":     "extra1",
    "extra2":     "extra2",
}

# Fontes padrão por tipo de campo (alinhado ao editor visual)
DEFAULT_FIELD_FONTS = {
    "name":       "CYGroteskWide-Bold.ttf",
    "title":      "Montserrat-Regular.ttf",
    "phone":      "Montserrat-Regular.ttf",
    "email":      "Montserrat-Regular.ttf",
    "department": "Montserrat-Regular.ttf",
    "website":    "Montserrat-Regular.ttf",
    "instagram":  "Montserrat-Regular.ttf",
    "extra1":     "Montserrat-Regular.ttf",
    "extra2":     "Montserrat-Regular.ttf",
}

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}

# Fontes padrão bundled (fallback)
SYSTEM_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def find_system_font(bold=False):
    """Localiza uma fonte disponível no sistema."""
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        ]
    else:
        candidates = SYSTEM_FONTS
    for f in candidates:
        if Path(f).exists():
            return f
    return None


class SignatureGenerator:
    """
    Gera imagens de assinatura personalizadas para cada funcionário.

    Parâmetros:
        base_image_path: Caminho para a imagem base (sem dados).
        fields: Lista de dicionários com configuração de cada campo.
                Cada campo tem:
                  - field_type: str  (ex: "name", "title", "phone" …)
                  - x, y:       int  (posição em pixels)
                  - font_size:  int  (ex: 16)
                  - color:      str  (ex: "#FFFFFF")
                  - bold:       bool
                  - font_file:  str  (nome do arquivo .ttf na pasta fonts/, opcional)
        output_dir: Pasta onde as imagens geradas serão salvas.
        font_dir:   Pasta onde fontes customizadas (.ttf) estão armazenadas.
    """

    def __init__(self, base_image_path: str, fields: list,
                 output_dir: str, font_dir: str = "",
                 target_width: int = 600):
        self.base_image_path = base_image_path
        self.fields          = fields
        self.output_dir      = output_dir
        self.font_dir        = font_dir
        self.target_width    = target_width  # Largura final da imagem em pixels
        self._custom_fonts   = self._index_custom_fonts()
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def _index_custom_fonts(self) -> dict:
        """Indexa fontes customizadas por nome (case-insensitive)."""
        indexed = {}
        if not self.font_dir:
            return indexed

        font_root = Path(self.font_dir)
        if not font_root.exists():
            return indexed

        for item in font_root.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() not in FONT_EXTENSIONS:
                continue
            indexed[item.name.lower()] = item
        return indexed

    @staticmethod
    def _normalize_font_file(font_file: str) -> str:
        """Normaliza o nome da fonte removendo aspas, espaços e caminho."""
        if not font_file:
            return ""
        value = str(font_file).strip().strip('"').strip("'").replace("\\", "/")
        if "/" in value:
            value = value.split("/")[-1]
        return value

    @staticmethod
    def _bold_variants(font_name: str) -> list:
        """Gera nomes alternativos para tentar versão Bold da mesma fonte."""
        name = SignatureGenerator._normalize_font_file(font_name)
        if not name:
            return []

        stem = Path(name).stem
        suffix = Path(name).suffix or ".ttf"
        variants = []

        replacements = [
            ("-Regular", "-Bold"),
            ("_Regular", "_Bold"),
            (" Regular", " Bold"),
            ("Regular", "Bold"),
            ("-regular", "-bold"),
            ("_regular", "_bold"),
            (" regular", " bold"),
            ("regular", "bold"),
            ("-Light", "-Bold"),
            ("-light", "-bold"),
            ("-Medium", "-Bold"),
            ("-medium", "-bold"),
            ("-SemiBold", "-Bold"),
            ("-semibold", "-bold"),
        ]

        for old, new in replacements:
            if old in stem:
                variants.append(stem.replace(old, new) + suffix)

        if "bold" not in stem.lower():
            variants.append(f"{stem}-Bold{suffix}")
            variants.append(f"{stem}_Bold{suffix}")

        deduped = []
        seen = set()
        for variant in variants:
            key = variant.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(variant)
        return deduped

    def _find_custom_font(self, font_name: str) -> Optional[Path]:
        """Busca fonte customizada por nome, ignorando maiúsculas/minúsculas."""
        normalized = self._normalize_font_file(font_name)
        if not normalized:
            return None

        exact = self._custom_fonts.get(normalized.lower())
        if exact:
            return exact

        # Fallback por stem (aceita nome sem extensão ou extensão diferente)
        expected_stem = Path(normalized).stem.lower()
        for filename, path in self._custom_fonts.items():
            if Path(filename).stem.lower() == expected_stem:
                return path

        return None

    def _get_font(self, field: dict) -> ImageFont.FreeTypeFont:
        """Carrega a fonte configurada para o campo, com fallback."""
        size       = int(field.get("font_size", 14))
        bold       = bool(field.get("bold", False))
        field_type = field.get("field_type", "")
        font_file  = self._normalize_font_file(field.get("font_file", ""))

        # 1. Fonte customizada na pasta fonts/
        candidates = []
        if font_file:
            candidates.append(font_file)

        default_font = DEFAULT_FIELD_FONTS.get(field_type, "")
        if default_font and default_font not in candidates:
            candidates.append(default_font)

        resolved_candidates = []
        for candidate in candidates:
            if bold:
                resolved_candidates.extend(self._bold_variants(candidate))
            resolved_candidates.append(candidate)

        seen = set()
        for candidate in resolved_candidates:
            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)

            custom = self._find_custom_font(candidate)
            if not custom:
                continue

            try:
                return ImageFont.truetype(str(custom), size)
            except OSError:
                # Fonte corrompida/incompatível: tenta próximos candidatos.
                continue

        # 2. Fonte do sistema
        sys_font = find_system_font(bold=bold)
        if sys_font:
            return ImageFont.truetype(sys_font, size)

        # 3. Fallback absoluto
        return ImageFont.load_default()

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        """Converte #RRGGBB → (R, G, B)."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b)

    def _get_value(self, field: dict, emp: dict) -> str:
        """Retorna o valor do campo para o funcionário, com prefixo opcional."""
        ftype   = field.get("field_type", "")
        key     = FIELD_KEYS.get(ftype, ftype)
        value   = emp.get(key, "") or ""
        prefix  = field.get("prefix", "")
        suffix  = field.get("suffix", "")
        if value:
            return f"{prefix}{value}{suffix}"
        return ""

    def generate(self, emp: dict) -> str:
        """
        Gera a imagem de assinatura para um funcionário.
        Retorna o nome do arquivo gerado (sem o diretório).
        """
        base_img  = Image.open(self.base_image_path).convert("RGBA")
        overlay   = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
        draw      = ImageDraw.Draw(overlay)

        for field in self.fields:
            if not field.get("visible", True):
                continue

            text  = self._get_value(field, emp)
            if not text:
                continue

            x     = int(field.get("x", 0))
            y     = int(field.get("y", 0))
            color = field.get("color", "#FFFFFF")
            align = field.get("align", "left")  # left | center | right
            font  = self._get_font(field)

            # Ajuste de alinhamento horizontal
            if align in ("center", "right"):
                bbox = draw.textbbox((0, 0), text, font=font)
                tw   = bbox[2] - bbox[0]
                max_w = int(field.get("max_width", base_img.width))
                if align == "center":
                    x = x - tw // 2
                else:
                    x = x - tw

            # Sombra sutil (opcional)
            if field.get("shadow", False):
                shadow_color = (0, 0, 0, 120)
                draw.text((x + 1, y + 1), text, font=font, fill=shadow_color)

            # Trunca o texto se ultrapassar a borda direita da imagem
            max_x = base_img.width - 4
            while len(text) > 1:
                bbox = draw.textbbox((x, y), text, font=font)
                if bbox[2] <= max_x:
                    break
                text = text[:-1]

            rgb = self._hex_to_rgb(color)
            draw.text((x, y), text, font=font, fill=(*rgb, 255))

        # Mescla a camada de texto com a imagem base
        result = Image.alpha_composite(base_img, overlay).convert("RGB")

        # Redimensiona para a largura padrão (mantém proporção)
        if self.target_width and result.width != self.target_width:
            ratio      = self.target_width / result.width
            new_height = int(result.height * ratio)
            result     = result.resize(
                (self.target_width, new_height),
                Image.LANCZOS
            )

        # Nome do arquivo: baseado no email do funcionário
        safe_email = re.sub(r"[^a-z0-9]", "_", emp.get("email", "unknown").lower())
        filename   = f"{safe_email}.png"
        out_path   = Path(self.output_dir) / filename
        result.save(str(out_path), "PNG", optimize=True)

        return filename

    def preview_fields(self, emp: dict) -> list:
        """
        Retorna lista de campos que seriam renderizados para este funcionário.
        Útil para debug.
        """
        return [
            {
                "field_type": f.get("field_type"),
                "value":      self._get_value(f, emp),
                "x":          f.get("x"),
                "y":          f.get("y"),
            }
            for f in self.fields
            if self._get_value(f, emp)
        ]
