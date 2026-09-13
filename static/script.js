let stockState = 0;

document.getElementById("toggleStockBtn").addEventListener("click", async () => {
  const res = await fetch("/api/toggle-stock", { method: "POST" });
  const data = await res.json();
  stockState = data.new_stock;
  document.getElementById("toggleStockBtn").innerText = `Simulate Stock: ${stockState > 0 ? "In Stock (5)" : "Out of Stock (0)"}`;
});

document.getElementById("sendBtn").addEventListener("click", sendMessage);

async function sendMessage() {
  const input = document.getElementById("userInput");
  const text = input.value.trim();
  if (!text) return;

  const chatBox = document.getElementById("chatBox");
  chatBox.innerHTML += `<div class="msg user">${text}</div>`;
  input.value = "";
  chatBox.scrollTop = chatBox.scrollHeight;

  const logsContainer = document.getElementById("logsContainer");
  logsContainer.innerHTML = `<div class="log-card"><div class="log-step">Agent Activated</div>Running Autonomous Resolution...</div>`;

  try {
    const res = await fetch("/api/agent-resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, order_id: "ORD-9901" })
    });
    
    const data = await res.json();

    // Render Logs step-by-step
    logsContainer.innerHTML = "";
    data.logs.forEach((log) => {
      let isReplan = log.step.includes("Replanning");
      let isVerified = log.step.includes("Verification");

      let cardClass = isReplan ? "log-card replan" : isVerified ? "log-card verified" : "log-card";
      let content = log.detail || `<pre>${JSON.stringify(log.output || log.tool, null, 2)}</pre>`;
      
      logsContainer.innerHTML += `
        <div class="${cardClass}">
          <div class="log-step">${log.step} ${log.tool ? `-> ${log.tool}()` : ""}</div>
          <div>${content}</div>
        </div>
      `;
    });

    // Update Chat reply
    chatBox.innerHTML += `<div class="msg bot">${data.reply}</div>`;
    chatBox.scrollTop = chatBox.scrollHeight;

    // Update DB Inspector View
    document.getElementById("dbStateViewer").innerText = JSON.stringify(data.final_order_state, null, 2);

  } catch (err) {
    console.error(err);
  }
}