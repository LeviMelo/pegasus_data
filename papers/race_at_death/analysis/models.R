# The spatial and multilevel models of the paper, on the tables spatial.py prepares in data/spatial/.
#   Rscript models.R <data/spatial> [areal|individual]
# areal: BYM2 small-area models of the infant linkage by municipality (R-INLA), the region-year panel of convergence
#        (lme4) and the mortality rate ratio by immediate region (R-INLA, Poisson BYM2).
# individual: multilevel logistic models of the certified race of linked infants (lme4), on data/spatial/individual.parquet.
# INLA settings: no PARDISO on this machine; TAUCS with the Gaussian approximation and empirical-Bayes hyperparameters
# (strategy "gaussian", int.strategy "eb"), which a benchmark ran in under a minute per municipal model.
suppressPackageStartupMessages({library(INLA); library(arrow); library(lme4); library(splines); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
sp <- args[1]
stage <- if (length(args) > 1) args[2] else "areal"
out <- list()
t_all <- Sys.time()
say <- function(...) { cat(format(Sys.time(), "%H:%M:%S"), ..., "\n"); flush.console() }

graph_of <- function(i, j, n) inla.read.graph(Matrix::sparseMatrix(i = c(i, j), j = c(j, i), x = 1, dims = c(n, n)))
HYP <- list(phi = list(prior = "pc", param = c(0.5, 0.5)), prec = list(prior = "pc.prec", param = c(1, 0.01)))
fit_inla <- function(formula, data, family = "binomial", ...) {
  inla(formula, family = family, data = data, num.threads = "4:1", inla.mode = "compact",
       control.inla = list(int.strategy = "eb", strategy = "gaussian"), control.compute = list(dic = TRUE, waic = FALSE),
       control.predictor = list(compute = TRUE, link = 1), ...)
}
hyper <- function(fit, name = "idx") {
  h <- fit$summary.hyperpar
  prec <- h[paste("Precision for", name), "mean"]
  list(sd_total = 1 / sqrt(prec), phi = h[paste("Phi for", name), "mean"], phi_sd = h[paste("Phi for", name), "sd"], dic = fit$dic$dic)
}

if (stage == "areal") {
  M <- as.data.frame(read_parquet(file.path(sp, "municipal.parquet")))
  E <- as.data.frame(read_parquet(file.path(sp, "edges.parquet")))
  n <- nrow(M)
  g <- graph_of(E$i, E$j, n)
  M$lws <- qlogis(pmin(pmax(M$white_share, 0.005), 0.995))
  M$state <- factor(M$uf)
  M$lgdp <- log(M$gdp_pc); M$lpop <- log(M$pop2010)
  fill <- function(v) { v[!is.finite(v)] <- median(v[is.finite(v)]); v }
  for (v in c("lws", "lgdp", "lpop", "illiterate", "urban", "physicians_1000", "natural_by_svo", "external_by_iml", "died_hospital", "race_blank"))
    M[[v]] <- fill(M[[v]])
  M$capital <- as.integer(M$capital %in% TRUE); M$metro <- as.integer(M$metro %in% TRUE)
  zs <- function(v) (v - mean(v)) / sd(v)
  for (v in c("lgdp", "lpop", "illiterate", "urban", "physicians_1000", "natural_by_svo", "external_by_iml", "died_hospital", "race_blank"))
    M[[paste0("z_", v)]] <- zs(M[[v]])
  CONTEXT <- "z_lgdp + z_illiterate + z_urban + z_lpop + capital + metro + z_physicians_1000 + z_natural_by_svo + z_external_by_iml + z_died_hospital + z_race_blank"
  OUT <- list(
    PW = c("PW", "nP"), WP = c("WP", "nW"), KK = c("KK", "nK"), KP = c("KP", "nK"), WW = c("WW", "nW"), PP = c("PP", "nP"),
    disagree = c("disagree", "n"), famPW = c("famPW_y", "famP_rec"), famKK = c("famKK_y", "famK_rec"))
  M$disagree <- M$n - M$agree
  M$famPW_y <- round(ifelse(is.na(M$famPW), 0, M$famPW) * ifelse(is.na(M$famP_rec), 0, M$famP_rec))
  M$famKK_y <- round(ifelse(is.na(M$famKK), 0, M$famKK) * ifelse(is.na(M$famK_rec), 0, M$famK_rec))
  M$famP_rec[is.na(M$famP_rec)] <- 0; M$famK_rec[is.na(M$famK_rec)] <- 0; M$famP_rec <- round(M$famP_rec); M$famK_rec <- round(M$famK_rec)
  est <- data.frame(mun = M$mun)
  FULL <- c("PW", "KK", "disagree", "famPW")
  for (o in names(OUT)) {
    d <- data.frame(y = M[[OUT[[o]][1]]], N = M[[OUT[[o]][2]]], idx = M$idx, M[, c("lws", "state", grep("^z_|capital|metro", names(M), value = TRUE))])
    d$y[d$N == 0] <- NA; d$N[d$N == 0] <- 1                 # no trials: predicted from the field, not observed
    f0 <- y ~ 1 + f(idx, model = "bym2", graph = g, scale.model = TRUE, constr = TRUE, hyper = HYP)
    t0 <- Sys.time()
    m0 <- fit_inla(f0, d, Ntrials = d$N)
    say(o, "M0", round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s")
    est[[paste0(o, "_mean")]] <- m0$summary.fitted.values$mean
    est[[paste0(o, "_lo")]] <- m0$summary.fitted.values$`0.025quant`
    est[[paste0(o, "_hi")]] <- m0$summary.fitted.values$`0.975quant`
    est[[paste0(o, "_sd")]] <- m0$summary.fitted.values$sd
    res <- list(M0 = hyper(m0), intercept = plogis(m0$summary.fixed["(Intercept)", "mean"]), observed = sum(d$y, na.rm = TRUE), trials = sum(d$N[!is.na(d$y)]))
    if (o %in% FULL) {
      forms <- list(
        M1_composition = update(f0, . ~ . + ns(lws, df = 3)),
        M2_state = update(f0, . ~ . + state),
        M3_composition_state = update(f0, . ~ . + ns(lws, df = 3) + state),
        M4_context = as.formula(paste("y ~ 1 + f(idx, model = 'bym2', graph = g, scale.model = TRUE, constr = TRUE, hyper = HYP) +", CONTEXT)),
        M5_composition_context = as.formula(paste("y ~ 1 + ns(lws, df = 3) + f(idx, model = 'bym2', graph = g, scale.model = TRUE, constr = TRUE, hyper = HYP) +", CONTEXT)),
        M6_all = as.formula(paste("y ~ 1 + ns(lws, df = 3) + state + f(idx, model = 'bym2', graph = g, scale.model = TRUE, constr = TRUE, hyper = HYP) +", CONTEXT)))
      for (k in names(forms)) {
        t0 <- Sys.time()
        mk <- fit_inla(forms[[k]], d, Ntrials = d$N)
        say(o, k, round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s")
        fx <- mk$summary.fixed
        res[[k]] <- c(hyper(mk), list(fixed = lapply(split(fx[, c("mean", "sd", "0.025quant", "0.975quant")], rownames(fx)), as.list)))
        if (k == "M3_composition_state") {       # the residual field after composition and state: for Moran's I and the border test
          est[[paste0(o, "_resid_field")]] <- mk$summary.random$idx$mean[1:n]
        }
        if (k == "M1_composition") est[[paste0(o, "_comp_field")]] <- mk$summary.random$idx$mean[1:n]
        if (k == "M2_state") {
          sf <- fx[grepl("^state", rownames(fx)), "mean"]
          res[[k]]$state_effects <- as.list(setNames(c(0, sf), levels(d$state)))
        }
        if (k == "M3_composition_state") {
          sf <- fx[grepl("^state", rownames(fx)), "mean"]
          res[[k]]$state_effects <- as.list(setNames(c(0, sf), levels(d$state)))
        }
      }
    }
    out$bym2[[o]] <- res
  }
  write_parquet(est, file.path(sp, "bym2_estimates.parquet"))

  # ---------------------------------------------------------------- the region-year panel: convergence of the certificate to the mother
  P <- as.data.frame(read_parquet(file.path(sp, "panel.parquet")))
  P$yc <- (P$year - 2018) / 10                                     # per decade, centred on 2018
  P$macro <- factor(floor(P$uf / 10), labels = c("North", "Northeast", "Southeast", "South", "Centre-West"))
  P$intermediate <- factor(P$intermediate)
  for (o in list(c("WW", "isW"), c("PP", "isP"), c("KK", "isK"), c("agree", "n"), c("PW", "isP"))) {
    d <- P[P[[o[2]]] > 0, ]
    t0 <- Sys.time()
    m <- glmer(cbind(d[[o[1]]], d[[o[2]]] - d[[o[1]]]) ~ yc + (1 + yc | intermediate), data = d, family = binomial,
               control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5)))
    mm <- glmer(cbind(d[[o[1]]], d[[o[2]]] - d[[o[1]]]) ~ yc * macro + (1 + yc | intermediate), data = d, family = binomial,
                control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5)))
    say("panel", o[1], round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s")
    vc <- as.data.frame(VarCorr(m))
    re <- ranef(m, condVar = TRUE)$intermediate
    pv <- attr(re, "postVar")
    fx <- summary(m)$coefficients; fxm <- summary(mm)$coefficients
    out$panel[[o[1]]] <- list(
      fixed = lapply(split(as.data.frame(fx), rownames(fx)), as.list), by_macro = lapply(split(as.data.frame(fxm), rownames(fxm)), as.list),
      sd_intercept = vc$sdcor[1], sd_slope = vc$sdcor[2], cor_intercept_slope = vc$sdcor[3],
      lrt_slope_varies = anova(update(m, . ~ yc + (1 | intermediate)), m)[2, "Pr(>Chisq)"],
      regions = data.frame(intermediate = rownames(re), intercept = fx["(Intercept)", "Estimate"] + re[, 1], slope = fx["yc", "Estimate"] + re[, 2],
                           slope_se = sqrt(pv[2, 2, ]), intercept_se = sqrt(pv[1, 1, ])))
  }

  # ---------------------------------------------------------------- mortality rate ratio White to Brown by immediate region, three classifications
  A <- as.data.frame(read_parquet(file.path(sp, "immediate.parquet")))
  A <- A[!is.na(A$immediate), ]
  RE <- as.data.frame(read_parquet(file.path(sp, "immediate_edges.parquet")))
  A$r <- seq_len(nrow(A))
  key <- setNames(A$r, A$immediate)
  ga <- graph_of(key[as.character(RE$a)], key[as.character(RE$b)], nrow(A))
  for (cl in list(c("mother", "mothDW", "mothDP", "birthsW", "birthsP"), c("certificate", "certW", "certP", "birthsW", "birthsP"),
                  c("family", "famDW", "famDP", "famBW", "famBP"))) {
    d <- rbind(data.frame(y = round(A[[cl[2]]]), E = A[[cl[4]]], white = 1, r = A$r, r2 = A$r),
               data.frame(y = round(A[[cl[3]]]), E = A[[cl[5]]], white = 0, r = A$r, r2 = A$r))
    d <- d[d$E > 0, ]
    t0 <- Sys.time()
    m <- fit_inla(y ~ white + f(r, model = "bym2", graph = ga, scale.model = TRUE, constr = TRUE, hyper = HYP) +
                    f(r2, white, model = "bym2", graph = ga, scale.model = TRUE, constr = TRUE, hyper = HYP),
                  d, family = "poisson", E = d$E)
    say("ratio", cl[1], round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s")
    b <- m$summary.fixed["white", ]
    f2 <- m$summary.random$r2[seq_len(nrow(A)), ]
    out$ratio[[cl[1]]] <- list(national = list(mean = b$mean, sd = b$sd), hyper = hyper(m, "r2"),
                               regions = data.frame(immediate = A$immediate, log_rr = b$mean + f2$mean, sd = sqrt(b$sd^2 + f2$sd^2),
                                                    raw_rr = (A[[cl[2]]] / A[[cl[4]]]) / (A[[cl[3]]] / A[[cl[5]]]), deaths_white = A[[cl[2]]], deaths_brown = A[[cl[3]]]))
  }
  out$seconds <- as.numeric(difftime(Sys.time(), t_all, units = "secs"))
  write(toJSON(out, auto_unbox = TRUE, digits = NA, null = "null", na = "null"), file.path(sp, "areal.json"))
  say("areal done", round(out$seconds), "s")
}

# ---------------------------------------------------------------- individual: multilevel logistic models of linked infants
# For each mother's race, the certified race as an outcome; municipality random intercepts; a sequence of fixed parts that
# sets composition, the socioeconomic context, the health services and the recording quality against one another
# (the proportional change in the municipal variance, PCV, and the median odds ratio, MOR). Sequence fitted with nAGQ = 0
# (PIRLS), the full model with its fixed effects reported, and with a crossed random intercept for the establishment of death.
if (stage == "individual") {
  I <- as.data.frame(read_parquet(file.path(sp, "individual.parquet")))
  lv <- function(v, ref) relevel(factor(v), ref = ref)
  I$certifier <- lv(I$certifier, "attending physician"); I$death_place <- lv(I$death_place, "hospital"); I$school <- lv(I$school, "8-11")
  I$mother_age <- lv(I$mother_age, "20-34"); I$low_weight <- lv(I$low_weight, ">=2500 g"); I$age_group <- lv(I$age_group, "0-6 days")
  I$cause_group <- lv(I$cause_group, "perinatal")
  I$region <- factor(I$region, levels = c(3, 1, 2, 4, 5), labels = c("Southeast", "North", "Northeast", "South", "Centre-West"))
  I$yc <- (I$year - 2018) / 10
  I$capital <- as.integer(I$capital %in% TRUE); I$metro <- as.integer(I$metro %in% TRUE)
  zs <- function(v) { v[!is.finite(v)] <- median(v[is.finite(v)]); (v - mean(v)) / sd(v) }
  I$z_lgdp <- zs(log(I$gdp_pc)); I$z_illit <- zs(I$illiterate); I$z_urban <- zs(I$urban); I$z_lpop <- zs(log(I$pop2010))
  I$z_phys <- zs(I$physicians_1000); I$z_svo <- zs(I$natural_by_svo); I$z_iml <- zs(I$external_by_iml); I$z_hosp <- zs(I$died_hospital)
  I$z_blank <- zs(I$race_blank)
  I$death_estab[I$death_estab == "none"] <- paste0("none_", I$mun[I$death_estab == "none"])
  COMP <- "ns(lws, df = 3)"
  SOC <- "z_lgdp + z_illit + z_urban + z_lpop + capital + metro"
  SVC <- "z_phys + z_svo + z_iml + z_hosp + z_blank"
  IND <- "region + yc + certifier + death_place + age_group + cause_group + school + mother_age + low_weight"
  SEQ <- list(null = "1", composition = COMP, socioeconomic = SOC, services = SVC, composition_socioeconomic = paste(COMP, "+", SOC),
              socioeconomic_services = paste(SOC, "+", SVC), composition_socioeconomic_services = paste(COMP, "+", SOC, "+", SVC),
              full = paste(COMP, "+", SOC, "+", SVC, "+", IND), individual_only = IND)
  CTRL <- glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5), calc.derivs = FALSE)
  var_mun <- function(m) as.data.frame(VarCorr(m))$vcov[as.data.frame(VarCorr(m))$grp == "mun"]
  tidy <- function(m) {
    co <- summary(m)$coefficients
    lapply(split(as.data.frame(co), rownames(co)), function(r) list(est = r[[1]], se = r[[2]]))
  }
  OUTS <- list(brown_white = list(sub = "brown", y = "y_white"), brown_brown = list(sub = "brown", y = "y_brown"), black_black = list(sub = "black", y = "y_black"),
               black_brown = list(sub = "black", y = "y_brown"), white_white = list(sub = "white", y = "y_white"))
  for (o in names(OUTS)) {
    d <- I[I$dec == OUTS[[o]]$sub, ]
    d$y <- d[[OUTS[[o]]$y]]
    res <- list(n = nrow(d), events = sum(d$y), municipalities = length(unique(d$mun)))
    for (k in names(SEQ)) {
      t0 <- Sys.time()
      m <- glmer(as.formula(paste("y ~", SEQ[[k]], "+ (1 | mun)")), data = d, family = binomial, nAGQ = 0, control = CTRL)
      s2 <- var_mun(m)
      res$sequence[[k]] <- list(var_mun = s2, mor = exp(sqrt(2 * s2) * qnorm(0.75)), aic = AIC(m), icc = s2 / (s2 + pi^2 / 3))
      if (k == "composition_socioeconomic_services") res$fixed_context <- tidy(m)
      if (k == "socioeconomic") res$fixed_socioeconomic <- tidy(m)
      say("individual", o, k, round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s var", round(s2, 3))
    }
    v0 <- res$sequence$null$var_mun
    for (k in names(SEQ)) res$sequence[[k]]$pcv <- 1 - res$sequence[[k]]$var_mun / v0
    t0 <- Sys.time()
    agq <- 0                     # PIRLS: a Laplace refit (nAGQ = 1) of the 45 fixed effects ran over 13 minutes without converging for one outcome
    mf <- glmer(as.formula(paste("y ~", SEQ$full, "+ (1 | mun)")), data = d, family = binomial, nAGQ = agq, control = CTRL)
    res$full_laplace <- list(fixed = tidy(mf), var_mun = var_mun(mf), nAGQ = agq)
    say("individual", o, "full Laplace", round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s")
    if (o %in% c("brown_white", "black_black")) {
      t0 <- Sys.time()
      me <- glmer(as.formula(paste("y ~", SEQ$full, "+ (1 | mun) + (1 | death_estab)")), data = d, family = binomial, nAGQ = 0, control = CTRL)
      vc <- as.data.frame(VarCorr(me))
      res$establishment <- list(var_mun = vc$vcov[vc$grp == "mun"], var_estab = vc$vcov[vc$grp == "death_estab"],
                                establishments = length(unique(d$death_estab)), aic = AIC(me), aic_without = res$sequence$full$aic)
      say("individual", o, "establishment", round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s")
    }
    out$individual[[o]] <- res
    write(toJSON(out, auto_unbox = TRUE, digits = NA, null = "null", na = "null"), file.path(sp, "individual.json"))
  }
  say("individual done")
}
