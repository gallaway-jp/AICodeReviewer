const express = require("express");

function createRouter(repo) {
  const router = express.Router();

  router.get("/accounts/:accountId", async (req, res) => {
    const account = await repo.loadAccount(req.params.accountId);
    res.json(account);
  });

  return router;
}

module.exports = { createRouter };