# Between and within: does a municipality's certificate change when the municipality changes?
#   Rscript panel.R <data dir>      (reads panel_mun_year.parquet and panel_census.parquet from analysis/panel.py)
# Mundlak models (a random intercept for the place, each yearly variable split into the place's mean over 2013-2023 and the
# year's deviation from it, year effects): the between coefficient is the cross-sectional gradient, the within one what
# follows a change inside the same place. Fitted on municipality-years and again on immediate-region-years, where the yearly
# composition of births rests on more births. Then the two censuses: the change in the certificate between 2013-2015 and
# 2021-2023 against the change in the census share of White residents between 2010 and 2022. Writes results/panel.json.
suppressPackageStartupMessages({library(arrow); library(lme4); library(jsonlite)})
args <- commandArgs(trailingOnly = TRUE)
dd <- args[1]
P <- as.data.frame(read_parquet(file.path(dd, "panel_mun_year.parquet")))
C <- as.data.frame(read_parquet(file.path(dd, "panel_census.parquet")))
lg <- function(p) { p <- pmin(pmax(p, 0.005), 0.995); log(p / (1 - p)) }
VARS <- c("lw", "lgdp", "lphys", "blank", "svo", "iml")
LAB <- c(lw = "composition (logit of White births)", lgdp = "GDP per capita (log)", lphys = "physicians per 1,000 (log)",
         blank = "race left blank on certificates", svo = "natural deaths certified by a verification service",
         iml = "external deaths certified by a medical examiner")

prepare <- function(D, unit) {
  D$lw <- lg(D$white_births)
  D$lgdp <- log(D$gdp_pc)
  D$lphys <- log(D$physicians_1000 + 0.1)
  D$blank <- D$race_blank
  D$svo <- D$natural_svo
  D$iml <- D$external_iml
  for (v in VARS) {
    m <- ave(D[[v]], D[[unit]], FUN = function(x) mean(x, na.rm = TRUE))
    D[[v]] <- ifelse(is.na(D[[v]]), m, D[[v]])            # a year with no such deaths takes the place's mean: no within change
    D[[paste0(v, "_b")]] <- m
    D[[paste0(v, "_w")]] <- D[[v]] - m
  }
  D$yr <- factor(D$year)
  D$ry <- factor(paste(substr(as.character(D[[unit]]), 1, 1), D$year))   # region by year: the first digit of a municipality or immediate region code
  D
}

aggregate_imm <- function(P) {
  S <- c("births", "births_race", "births_white", "deaths", "race_blank_n", "natural_n", "natural_svo_n", "external_n", "external_iml_n",
         "population", "gdp", "cnes_physicians_professionals")
  Y <- grep("^(n|y)_", names(P), value = TRUE)
  A <- aggregate(P[, c(S, Y)], by = list(immediate = P$immediate, year = P$year), FUN = function(x) sum(x, na.rm = TRUE))
  A$white_births <- A$births_white / A$births_race
  A$gdp_pc <- 1e3 * A$gdp / A$population
  A$physicians_1000 <- 1e3 * A$cnes_physicians_professionals / A$population
  A$race_blank <- A$race_blank_n / A$deaths
  A$natural_svo <- A$natural_svo_n / A$natural_n
  A$external_iml <- A$external_iml_n / A$external_n
  A
}

coefs <- function(m) {
  s <- summary(m)$coefficients
  lapply(split(as.data.frame(s[, 1:2]), rownames(s)), function(r) list(est = r[[1]], se = r[[2]]))
}

fit <- function(D, key, unit, years) {
  n <- D[[paste0("n_", key)]]; y <- D[[paste0("y_", key)]]
  E <- D[n > 0 & D$year %in% years & is.finite(D$lgdp) & is.finite(D$lw), ]
  E$n <- E[[paste0("n_", key)]]; E$y <- E[[paste0("y_", key)]]
  E$unit <- factor(E[[unit]])
  f_comp <- cbind(y, n - y) ~ lw_b + lw_w + ry + (1 | unit)
  f_all <- as.formula(paste("cbind(y, n - y) ~", paste(c(paste0(VARS, "_b"), paste0(VARS, "_w")), collapse = " + "), "+ ry + (1 | unit)"))
  m1 <- glmer(f_comp, data = E, family = binomial, nAGQ = 0)
  m2 <- glmer(f_all, data = E, family = binomial, nAGQ = 0)
  # how much each variable moves inside a place, against how much it differs between places (by the deaths' weight)
  spread <- lapply(setNames(VARS, VARS), function(v) {
    w <- E$n
    list(sd_between = sqrt(weighted.mean((E[[paste0(v, "_b")]] - weighted.mean(E[[paste0(v, "_b")]], w))^2, w)),
         sd_within = sqrt(weighted.mean(E[[paste0(v, "_w")]]^2, w)))
  })
  # the yearly composition's sampling variance (logit of a binomial share of the year's births), against its within variance:
  # the share of the within variation that is real change, by which the within coefficient is attenuated
  wb <- pmin(pmax(E$white_births, 0.005), 0.995)
  sv <- weighted.mean(1 / (E$births_race * wb * (1 - wb)), E$n)
  reliability <- max(0, 1 - sv / spread$lw$sd_within^2)
  list(n_units = nlevels(E$unit), lw_sampling_var = sv, lw_reliability = reliability, n_unit_years = nrow(E), deaths = sum(E$n), years = range(E$year),
       units_with_change = sum(tapply(E$year, E$unit, function(x) length(unique(x))) > 1),
       composition = coefs(m1), all = coefs(m2), var_unit = c(composition = VarCorr(m1)$unit[1], all = VarCorr(m2)$unit[1]),
       spread = spread)
}

out <- list(labels = as.list(LAB))
M <- prepare(P, "mun")
A <- prepare(aggregate_imm(P), "immediate")
gdp_years <- sort(unique(P$year[is.finite(P$gdp)]))
for (key in c("PW", "KK", "PP", "WW")) {
  out[[key]] <- list(municipality = fit(M, key, "mun", gdp_years), immediate = fit(A, key, "immediate", gdp_years))
  cat(key, "done\n"); flush.console()
}

# the two censuses: the certificate's change between 2013-2015 and 2021-2023 against the change in the census White share
early <- aggregate(cbind(y = y_PW, n = n_PW) ~ mun, data = P[P$year <= 2015, ], FUN = sum)
late <- aggregate(cbind(y = y_PW, n = n_PW) ~ mun, data = P[P$year >= 2021, ], FUN = sum)
D <- merge(merge(early, late, by = "mun", suffixes = c("_e", "_l")), C, by = "mun")
D <- D[D$n_e >= 5 & D$n_l >= 5, ]
D$imm <- P$immediate[match(D$mun, P$mun)]
L2 <- rbind(data.frame(mun = D$mun, imm = D$imm, late = 0, y = D$y_e, n = D$n_e, cw = lg(D$census_white_2010), lit = D$literate_2010, urb = D$urban_2010),
            data.frame(mun = D$mun, imm = D$imm, late = 1, y = D$y_l, n = D$n_l, cw = lg(D$census_white_2022), lit = D$literate_2022, urb = D$urban_2022))
L2$cw_b <- ave(L2$cw, L2$mun); L2$cw_w <- L2$cw - L2$cw_b
L2$lit_b <- ave(L2$lit, L2$mun); L2$lit_w <- L2$lit - L2$lit_b
L2$urb_b <- ave(L2$urb, L2$mun); L2$urb_w <- L2$urb - L2$urb_b
mc <- glmer(cbind(y, n - y) ~ cw_b + cw_w + lit_b + lit_w + urb_b + urb_w + late + (1 | mun), data = L2, family = binomial, nAGQ = 0)
out$census <- list(municipalities = length(unique(L2$mun)), deaths = sum(L2$n), coef = coefs(mc),
                   change_census_white = list(mean = mean(D$census_white_2022 - D$census_white_2010, na.rm = TRUE),
                                              sd = sd(D$census_white_2022 - D$census_white_2010, na.rm = TRUE),
                                              sd_logit_within = sd(L2$cw_w[L2$late == 1], na.rm = TRUE) * sqrt(2), sd_logit_between = sd(L2$cw_b[L2$late == 1], na.rm = TRUE)))
write_json(out, file.path(dirname(dd), "results", "panel.json"), auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("written\n")
