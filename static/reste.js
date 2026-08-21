document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('erp-form');
  if (!form || !form.elements.reste_a_payer_rmb) return;
  const update = () => {
    requestAnimationFrame(() => {
      const total = parseFloat(form.elements.total_rmb.value) || 0;
      const received = parseFloat(form.elements.recu_payment_rmb.value) || 0;
      form.elements.reste_a_payer_rmb.value = (total - received).toFixed(2);
    });
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  document.getElementById('payments')?.addEventListener('click', update);
  update();
});
