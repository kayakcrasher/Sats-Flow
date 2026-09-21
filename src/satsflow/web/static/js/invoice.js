/* Poll the invoice status endpoint and update the UI live. */
(function () {
    document.addEventListener("DOMContentLoaded", function () {
        const box = document.getElementById("invoice-status");
        if (!box) return;

        const slug = box.dataset.slug;
        const donationId = box.dataset.donationId;
        if (!slug || !donationId) return;

        const url = `/c/${slug}/invoice/${donationId}/status`;

        function render(data) {
            if (data.status === "error") {
                box.innerHTML = `<h4>Status check failed</h4><p>${data.error}</p>`;
                return;
            }

            if (data.is_final || data.status === "confirmed") {
                box.classList.add("is-confirmed");
                box.innerHTML = `
                    <h4>Payment confirmed ✓</h4>
                    <p>${data.confirmations} confirmation(s). Thank you.</p>
                    ${data.txid ? `<p class="mono tiny">${data.txid}</p>` : ""}
                `;
                clearInterval(timer);
                return;
            }

            if (data.status === "pending") {
                box.classList.add("is-pending");
                box.innerHTML = `
                    <h4>Payment detected — waiting for confirmations</h4>
                    <p>${data.confirmations} confirmation(s) so far.</p>
                `;
                return;
            }

            if (data.status === "underpaid") {
                box.classList.add("is-warn");
                box.innerHTML = `
                    <h4>Underpaid</h4>
                    <p>Received ${data.received}, expected ${data.expected}.</p>
                `;
                return;
            }

            // not_found, overpaid, anything else
            box.innerHTML = `
                <h4>Waiting for payment…</h4>
                <p>This page will update when the transaction is detected on-chain.</p>
            `;
        }

        async function poll() {
            try {
                const r = await fetch(url, { headers: { "Accept": "application/json" } });
                if (!r.ok) return;
                render(await r.json());
            } catch (e) {
                // network blip; try again next tick
            }
        }

        const timer = setInterval(poll, 5000);
        poll();  // immediate first check
    });
})();
