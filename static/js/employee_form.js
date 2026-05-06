/**
 * employee_form.js — Normaliza campos de funcionário no frontend
 * Nome: caixa alta
 * Telefone: máscara (31) 9 7217-5910
 */

function normalizePhoneDigits(raw) {
  let digits = String(raw || "").replace(/\D/g, "");

  // Remove DDI 55 quando presente
  if (digits.startsWith("55") && digits.length > 11) {
    digits = digits.slice(2);
  }

  // Remove prefixo 0 quando vier antes do DDD
  if (digits.startsWith("0") && digits.length > 11) {
    digits = digits.slice(1);
  }

  return digits.slice(0, 11);
}

function formatPhoneMask(raw) {
  const digits = normalizePhoneDigits(raw);

  if (!digits) return "";
  if (digits.length <= 2) return `(${digits}`;
  if (digits.length <= 3) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
  if (digits.length <= 7) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;

  if (digits.length <= 10) {
    return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  }

  return `(${digits.slice(0, 2)}) ${digits.slice(2, 3)} ${digits.slice(3, 7)}-${digits.slice(7)}`;
}

function attachEmployeeInputFormatting() {
  document.querySelectorAll('input[name="name"]').forEach((input) => {
    const normalizeName = () => {
      input.value = input.value.toUpperCase();
    };

    input.addEventListener("input", normalizeName);
    normalizeName();
  });

  document.querySelectorAll('input[name="phone"]').forEach((input) => {
    const applyMask = () => {
      input.value = formatPhoneMask(input.value);
    };

    input.addEventListener("input", applyMask);
    input.addEventListener("blur", applyMask);
    applyMask();
  });
}

document.addEventListener("DOMContentLoaded", attachEmployeeInputFormatting);
