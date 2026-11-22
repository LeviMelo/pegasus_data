# Who certifies: crossed random intercepts for the certifying physician (CRM within state, filed 2014-2018), the establishment of death and
# the municipality of residence, for Brown mothers' infants certified White (PW) and Black mothers' infants certified Black (KK).
#   Rscript physician.R <data/spatial>      (reads physician.parquet from mechanism.py; writes results/physician.json)
# Laplace approximation (nAGQ = 1), the composition of the municipality's births as a fixed term. The variances say at which level the
# classification varies once the others are held: the physician (a person), the establishment (an institution), the municipality (a place).
suppressPackageStartupMessages({library(arrow); library(lme4); library(jsonlite)})
sp <- commandArgs(trailingOnly = TRUE)[1]
P <- as.data.frame(read_parquet(file.path(sp, "physician.parquet")))
P$death_estab[is.na(P$death_estab) | P$death_estab == ""] <- "none"
out <- list()
for (cell in list(c("PW", "brown"), c("KK", "black"))) {
  d <- P[P$dec == cell[2] & !is.na(P$lws), ]
  d$y <- d[[cell[1]]]
  d$certifier <- factor(ifelse(is.na(d$certifier), "9", d$certifier))
  fits <- list(
    all = glmer(y ~ lws + (1 | physician) + (1 | death_estab) + (1 | mun6), data = d, family = binomial, nAGQ = 1,
                control = glmerControl(optimizer = "bobyqa")),
    no_physician = glmer(y ~ lws + (1 | death_estab) + (1 | mun6), data = d, family = binomial, nAGQ = 1, control = glmerControl(optimizer = "bobyqa")),
    no_establishment = glmer(y ~ lws + (1 | physician) + (1 | mun6), data = d, family = binomial, nAGQ = 1, control = glmerControl(optimizer = "bobyqa")))
  res <- list(deaths = nrow(d), physicians = length(unique(d$physician)), establishments = length(unique(d$death_estab)),
              municipalities = length(unique(d$mun6)),
              physicians_with_5 = sum(table(d$physician) >= 5))
  for (k in names(fits)) {
    vc <- as.data.frame(VarCorr(fits[[k]]))
    res[[k]] <- c(setNames(as.list(vc$vcov), vc$grp), list(lws = fixef(fits[[k]])[["lws"]], aic = AIC(fits[[k]])))
  }
  # likelihood-ratio tests of each level given the other two
  res$lrt_physician <- anova(fits$no_physician, fits$all)[2, "Pr(>Chisq)"]
  res$lrt_establishment <- anova(fits$no_establishment, fits$all)[2, "Pr(>Chisq)"]
  out[[cell[1]]] <- res
  cat(cell[1], "done\n"); flush.console()
}
write_json(out, file.path(dirname(sp), "..", "results", "physician.json"), auto_unbox = TRUE, digits = NA, pretty = TRUE)
cat("written\n")
