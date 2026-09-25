// Sequential operations within each game deliberately retain Python insertion
// order. Parallelism is across independent games. All simulation arithmetic is
// signed int64.
typedef long long I;
__device__ I lo(I a, I b) { return a < b ? a : b; }
__device__ I hi(I a, I b) { return a > b ? a : b; }
struct Plant {
  I id, kind, row, col, health, state, due, burst_due;
};
struct Zombie {
  I id, kind, row, x, health, armor, state, slow_until, has_pole, vault_until,
      landing_x, bite_progress, move_remainder, target_id, previous_x, headless,
      age, speed, pole_speed;
};
struct Shot {
  I id, row, x, damage, icy, move_remainder;
};
struct Mower {
  I row, x, state, move_remainder, chomp_ticks;
};
struct Header {
  I tick, status, sun, next_id, spawn_index, defeated, wave, total_waves,
      total_spawns, np, nz, nq, accepted, reason, advanced, allowed, dig,
      enabled, gameplay_rng, sky_due, sky_drops;
};
struct Sim {
  Header *h;
  Plant *p;
  Zombie *z;
  Shot *q;
  Mower *m;
  I *cd, *sp, *ev, *ne;
  double *f;
  __device__ I random(I minimum, I maximum) {
    unsigned int x = (unsigned int)h->gameplay_rng;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    h->gameplay_rng = x;
    return minimum + x % (maximum - minimum + 1);
  }
  __device__ void emit(I kind, I id = 0, I a = 0, I b = 0, I c = 0, I d = 0,
                       I e = 0) {
    if (DIAGNOSTIC) {
      I *v = ev + 8 * (*ne);
      v[0] = kind;
      v[1] = h->tick;
      v[2] = id;
      v[3] = a;
      v[4] = b;
      v[5] = c;
      v[6] = d;
      v[7] = e;
      (*ne)++;
    }
  }
  __device__ I center(Plant &a) {
    return a.col * G_units_per_tile + G_units_per_tile / 2;
  }
  __device__ I dist(I &rem, I speed, bool slow = false) {
    I n = speed * (slow ? G_slow_numerator : G_slow_denominator) + rem;
    rem = n % (G_tick_rate * G_slow_denominator);
    return n / (G_tick_rate * G_slow_denominator);
  }
  __device__ void remove_p(I i, I why) {
    emit(1, p[i].id, why);
    for (I j = i + 1; j < h->np; j++)
      p[j - 1] = p[j];
    h->np--;
  }
  __device__ void remove_q(I i) {
    for (I j = i + 1; j < h->nq; j++)
      q[j - 1] = q[j];
    h->nq--;
  }
  __device__ void add_p(I kind, I row, I col) {
    Plant a = {h->next_id++,
               kind,
               row,
               col,
               PH[kind],
               kind == 4 ? 1 : kind == 3 ? 3 : 0,
               h->tick + PF[kind],
               0};
    if (kind == 0) a.due = h->tick + random(PF[kind], PFMAX[kind]);
    else if (kind == 1 || kind == 5 || kind == 7)
      a.due = h->tick + random(0, PI[kind]);
    p[h->np++] = a;
    emit(0, a.id, kind, row, col);
  }
  __device__ I target(I row, I left, I right, bool headed = false) {
    I best = -1;
    for (I i = 0; i < h->nz; i++)
      if (z[i].health > 0 && z[i].row == row && z[i].x >= left &&
          (!headed || !z[i].headless) &&
          z[i].x <= right &&
          (best < 0 || z[i].x < z[best].x ||
           (z[i].x == z[best].x && z[i].id < z[best].id)))
        best = i;
    return best;
  }
  __device__ I damage(I i, I amount, I source, bool swallow = false) {
    Zombie &a = z[i];
    if (a.health <= 0)
      return 0;
    I hp = a.health, ar = a.armor;
    if (swallow)
      a.health = a.armor = 0;
    else {
      I absorbed = lo(a.armor, amount);
      a.armor -= absorbed;
      a.health = hi(0, a.health - amount + absorbed);
    }
    I dh = hp - a.health, da = ar - a.armor;
    emit(5, a.id, source, dh, da);
    if (!a.headless && a.health < ZH[a.kind] / 3) {
      a.headless = 1;
      a.has_pole = 0;
      a.bite_progress = a.target_id = 0;
      h->defeated++;
      if (source != 0) f[source > 0 ? 0 : 1]++;
      emit(6, a.id, a.kind, a.row);
      if (a.health > 0) emit(18, a.id);
    }
    else if (source > 0) {
      f[2] += dh;
      f[3] += (double)dh / ZH[a.kind];
    }
    return dh + da;
  }
  __device__ void clear_dead() {
    I out = 0;
    for (I i = 0; i < h->nz; i++) {
      if (z[i].health <= 0) {
        emit(19, z[i].id);
      } else
        z[out++] = z[i];
    }
    h->nz = out;
  }
  __device__ void income(I amount, I source, I id = 0) {
    I before = h->sun;
    h->sun = lo(G_sun_cap, h->sun + amount);
    emit(4, id, source, h->sun - before, amount);
  }
  __device__ void shoot(Plant &a) {
    Shot shot = {h->next_id++, a.row,       center(a) + G_projectile_offset,
                 PD[a.kind],   a.kind == 5, 0};
    q[h->nq++] = shot;
    emit(7, shot.id, a.id);
  }
  __device__ void detonate(I i) {
    Plant a = p[i];
    I rad = a.kind == 3 ? 1 : 0;
    I left = (a.col - rad) * G_units_per_tile,
      right = (a.col + rad + 1) * G_units_per_tile;
    I hit = 0;
    for (I j = 0; j < h->nz; j++)
      if (hi(z[j].row - a.row, a.row - z[j].row) <= rad && left <= z[j].x &&
          z[j].x < right)
        hit += damage(j, PD[a.kind], a.id);
    if (!hit)
      f[8]++;
    emit(8, a.id, a.row, a.col, rad);
    remove_p(i, 1);
  }
  __device__ void swallow(I pi, I zi) {
    Plant &a = p[pi];
    damage(zi, 0, a.id, true);
    a.state = 9;
    a.due = h->tick + PANIM[a.kind] - PBITE[a.kind];
    emit(9, z[zi].id, a.id);
  }
  __device__ void plants() {
    for (I i = 0; i < h->np;) {
      Plant &a = p[i];
      I kind = a.kind;
      if (kind == 0) {
        if (h->tick >= a.due) {
          income(PS[kind], 1, a.id);
          a.due = h->tick + random(PI[kind], PIMAX[kind]);
        }
      } else if (kind == 1 || kind == 5 || kind == 7) {
        if (a.burst_due && h->tick >= a.burst_due) {
          shoot(a);
          a.burst_due = 0;
        }
        bool launch = h->tick >= a.due;
        if (launch) a.due = h->tick + PI[kind] - random(0, PJ[kind]);
        if ((launch || (kind == 7 && a.due - h->tick == PB[kind])) &&
            target(a.row, center(a), 9223372036854775807LL) >= 0)
          a.burst_due = h->tick + PW[kind];
      } else if (kind == 3 && h->tick >= a.due) {
        detonate(i);
        continue;
      } else if (kind == 4) {
        if (a.state == 1 && h->tick >= a.due) {
          a.state = 7;
          a.due = h->tick + PRISE[kind];
        } else if (a.state == 7 && h->tick >= a.due) {
          a.state = 2;
          emit(10, a.id);
        }
        if (a.state == 2 && target(a.row, a.col * G_units_per_tile,
                                   (a.col + 1) * G_units_per_tile - 1, true) >= 0) {
          detonate(i);
          continue;
        }
      } else if (kind == 6) {
        if (a.state == 8 && h->tick >= a.due) {
          I t = target(a.row, center(a), center(a) + G_units_per_tile, true);
          if (t >= 0 && !z[t].has_pole && z[t].state != 2) swallow(i, t);
          else {
            a.state = 10;
            a.due = h->tick + PANIM[kind] - PBITE[kind];
          }
        } else if (a.state == 9 && h->tick >= a.due) {
          a.state = 4;
          a.due = h->tick + PI[kind];
        } else if (a.state == 4 && h->tick >= a.due) {
          a.state = 10;
          a.due = h->tick + PRECOVER[kind];
        } else if (a.state == 10 && h->tick >= a.due)
          a.state = 0;
        if (a.state == 0) {
          I t = target(a.row, center(a), center(a) + G_units_per_tile, true);
          if (t >= 0) {
            a.state = 8;
            a.due = h->tick + PBITE[kind];
          }
        }
      }
      i++;
    }
  }
  __device__ void projectiles() {
    for (I i = 0; i < h->nq;) {
      Shot &a = q[i];
      I end = a.x + dist(a.move_remainder, G_projectile_speed);
      I t = target(a.row, a.x, end);
      if (t >= 0) {
        damage(t, a.damage, a.id);
        if (a.icy && z[t].health > 0) {
          z[t].slow_until = h->tick + G_slow_ticks;
          emit(11, z[t].id, z[t].slow_until);
        }
        remove_q(i);
      } else if (end > G_spawn_x + G_units_per_tile)
        remove_q(i);
      else {
        a.x = end;
        i++;
      }
    }
  }
  __device__ void move_z(I i, I end) {
    Zombie &a = z[i];
    while (true) {
      I best = -1;
      for (I j = 0; j < h->nq; j++)
        if (q[j].row == a.row && end <= q[j].x && q[j].x <= a.x &&
            (best < 0 || q[j].x > q[best].x ||
             (q[j].x == q[best].x && q[j].id < q[best].id)))
          best = j;
      if (best < 0)
        break;
      Shot b = q[best];
      damage(i, b.damage, b.id);
      if (b.icy && a.health > 0) {
        a.slow_until = h->tick + G_slow_ticks;
        emit(11, a.id, a.slow_until);
      }
      remove_q(best);
      if (a.health <= 0)
        break;
    }
    a.x = end;
  }
  __device__ void zombies() {
    for (I i = 0; i < h->nz; i++) {
      Zombie &a = z[i];
      if (a.health <= 0)
        continue;
      a.age++;
      if (a.headless && random(0, G_headless_decay_chance - 1) == 0) {
        I d = lo(a.health, ZH[a.kind] >= G_headless_large_health ?
                 G_headless_large_damage : G_headless_damage);
        a.health -= d;
        emit(20, a.id, d);
        if (a.health <= 0) continue;
      }
      if (a.state == 2) {
        if (h->tick < a.vault_until)
          continue;
        a.x = a.landing_x;
        a.state = 0;
        emit(12, a.id);
      }
      bool slow = h->tick < a.slow_until;
      I end = a.x - dist(a.move_remainder, a.has_pole ? a.pole_speed : a.speed,
                         slow);
      I best = -1;
      for (I j = 0; j < h->np; j++)
        if (!a.headless && p[j].row == a.row && p[j].health > 0 &&
            end <= center(p[j]) + G_contact_offset &&
            center(p[j]) + G_contact_offset <= a.x &&
            (best < 0 || p[j].col > p[best].col ||
             (p[j].col == p[best].col && p[j].id < p[best].id)))
          best = j;
      if (best < 0) {
        move_z(i, end);
        a.state = a.has_pole ? 1 : 0;
        a.bite_progress = a.target_id = 0;
        continue;
      }
      Plant &b = p[best];
      move_z(i, center(b) + G_contact_offset);
      if (a.health <= 0 || a.headless)
        continue;
      if (b.kind == 4 && b.state == 2) {
        detonate(best);
        continue;
      }
      if (a.has_pole) {
        a.has_pole = 0;
        a.state = 2;
        a.vault_until = h->tick + G_vault_ticks;
        a.landing_x = a.x - G_vault_distance;
        a.bite_progress = a.target_id = 0;
        emit(13, a.id, b.id);
        continue;
      }
      if (a.target_id != b.id) {
        a.bite_progress = 0;
        a.target_id = b.id;
      }
      a.state = 3;
      if (b.kind != 3 && a.age % (G_bite_ticks * (slow ? 2 : 1)) == 0) {
        I d = lo(b.health, G_bite_damage);
        b.health -= d;
        emit(14, b.id, a.id, d);
        if (b.kind == 2)
          f[7] += d;
      }
    }
  }
  __device__ void mowers() {
    for (I r = 0; r < 5; r++) {
      Mower &a = m[r];
      bool activated = false;
      double kills = f[1];
      if (a.state == 0) {
        for (I i = 0; i < h->nz; i++)
          if (z[i].health > 0 && !z[i].headless && z[i].row == r && z[i].x <= G_mower_trigger_x) {
            activated = true;
            break;
          }
        if (activated) {
          a.state = 1;
          a.chomp_ticks = G_mower_first_hit_ticks;
          emit(15, 0, r);
          f[5]++;
          f[6] += h->sun;
          for (I i = 0; i < h->nz; i++)
            if (z[i].row == r && z[i].x <= a.x)
              damage(i, 0, -r - 1, true);
        }
      }
      if (a.state == 1) {
        I speed = G_mower_speed;
        if (a.chomp_ticks) {
          a.chomp_ticks--;
          I d = G_mower_hit_ticks - 2 * a.chomp_ticks;
          speed = G_mower_min_speed + (speed - G_mower_min_speed) * d * d /
                  (G_mower_hit_ticks * G_mower_hit_ticks);
        }
        I end = a.x + dist(a.move_remainder, speed);
        for (I i = 0; i < h->nz; i++)
          if (z[i].row == r && z[i].health > 0 && z[i].x <= end &&
              z[i].previous_x >= a.x) {
            damage(i, 0, -r - 1, true);
            a.chomp_ticks = G_mower_hit_ticks;
          }
        a.x = end;
        if (a.x > G_spawn_x) {
          a.state = 2;
          emit(16, 0, r);
        }
      }
      if (activated && f[1] == kills)
        f[4]++;
    }
  }
  __device__ void advance() {
    h->tick++;
    h->advanced++;
    for (I i = 0; i < 8; i++)
      if (cd[i])
        cd[i]--;
    while (h->spawn_index < h->total_spawns &&
           sp[h->spawn_index * 5] <= h->tick) {
      I *s = sp + 5 * h->spawn_index;
      I k = s[1];
      Zombie a = {h->next_id++,
                  k,
                  s[2],
                  s[4],
                  ZH[k],
                  ZA[k],
                  k == 4 ? 1 : 0,
                  0,
                  k == 4,
                  0,
                  0,
                  0,
                  0,
                  0,
                  0};
      z[h->nz++] = a;
      z[h->nz - 1].speed = random(ZS[k], ZSMAX[k]);
      z[h->nz - 1].pole_speed = k == 4 ? random(ZP[k], ZPMAX[k]) : 0;
      h->spawn_index++;
      h->wave = hi(h->wave, s[3]);
      emit(3, a.id, k, a.row, s[3]);
    }
    if (h->tick >= h->sky_due) {
      income(G_sky_sun_amount, 0);
      h->sky_drops++;
      h->sky_due = h->tick + lo(G_sky_interval_max_ticks,
          G_sky_interval_base_ticks + h->sky_drops * G_sky_interval_increment_ticks)
          + random(0, G_sky_interval_jitter_ticks);
    }
    plants();
    projectiles();
    clear_dead();
    for (I i = 0; i < h->nz; i++)
      z[i].previous_x = z[i].x;
    zombies();
    mowers();
    clear_dead();
    for (I i = 0; i < h->np;)
      if (p[i].health <= 0)
        remove_p(i, 2);
      else
        i++;
    for (I i = 0; i < h->nz; i++)
      if (!z[i].headless && z[i].x <= G_house_x)
        h->status = 2;
    if (!h->status && h->defeated == h->total_spawns)
      h->status = 1;
    if (h->status)
      emit(17, 0, h->status);
  }
  __device__ I legality(I a, bool restricted = true) {
    if (h->status)
      return 6;
    if (a < 0 || a >= 406)
      return 7;
    if (a == 0)
      return 0;
    I tile = (a - 1) % 45, kind = (a - 1) / 45;
    I occupant = -1;
    for (I i = 0; i < h->np; i++)
      if (p[i].row == tile / 9 && p[i].col == tile % 9)
        occupant = i;
    if (kind == 8) {
      if (occupant < 0)
        return 4;
      if (restricted && !h->dig)
        return 5;
      return 0;
    }
    if (occupant >= 0)
      return 1;
    if (cd[kind])
      return 2;
    if (h->sun < PC[kind])
      return 3;
    if (restricted && !(h->allowed & (1 << kind)))
      return 5;
    return 0;
  }
  __device__ void step(I action, I ticks, bool per_tick) {
    *ne = 0;
    for (I i = 0; i < 9; i++)
      f[i] = 0;
    h->advanced = 0;
    h->reason = legality(action);
    h->accepted = h->reason == 0;
    if (!h->enabled || h->status)
      return;
    // Restricted tasks convert any masked action to Wait, just as the CPU
    // wrapper does.
    bool task = h->allowed != 255 || !h->dig;
    if (h->reason && task)
      h->reason = 5;
    if (h->accepted && action) {
      I tile = (action - 1) % 45, kind = (action - 1) / 45;
      if (kind < 8) {
        h->sun -= PC[kind];
        cd[kind] = PR[kind] + 1;
        add_p(kind, tile / 9, tile % 9);
      } else
        for (I i = 0; i < h->np; i++)
          if (p[i].row == tile / 9 && p[i].col == tile % 9) {
            remove_p(i, 0);
            break;
          }
    } else if (h->reason && h->reason != 5)
      emit(2, 0, h->reason);
    if (per_tick && action && h->accepted)
      return;
    for (I i = 0; i < ticks && !h->status; i++)
      advance();
  }
};
extern "C" __global__ void step_games(I *headers, I *plants, I *zombies,
                                      I *shots, I *mowers, I *cooldowns,
                                      I *schedules, I *events, I *event_counts,
                                      double *facts, const I *actions, I n,
                                      I ticks, I per_tick) {
  I i = blockIdx.x;
  if (threadIdx.x || i >= n)
    return;
  Sim s = {(Header *)(headers + i * GAME_HEADER_WIDTH),
           (Plant *)(plants + i * 45 * GAME_PLANT_WIDTH),
           (Zombie *)(zombies + i * ZCAP * GAME_ZOMBIE_WIDTH),
           (Shot *)(shots + i * QCAP * GAME_PROJECTILE_WIDTH),
           (Mower *)(mowers + i * 5 * GAME_MOWER_WIDTH),
           cooldowns + i * 8,
           schedules + i * ZCAP * 5,
           events + i * ECAP * 8,
           event_counts + i,
           facts + i * 9};
  s.step(actions[i], ticks, per_tick);
}
extern "C" __global__ void legal_masks(const I *headers, const I *plants,
                                       const I *cooldowns, bool *masks, I n) {
  I ix = blockDim.x * blockIdx.x + threadIdx.x;
  if (ix >= n * 406)
    return;
  I i = ix / 406, a = ix % 406;
  const Header &h = ((Header *)headers)[i];
  bool ok = h.status == 0 && h.enabled;
  if (a) {
    I tile = (a - 1) % 45, k = (a - 1) / 45;
    bool occupied = false;
    const Plant *p = (const Plant *)(plants + i * 45 * GAME_PLANT_WIDTH);
    for (I j = 0; j < h.np; j++)
      if (p[j].row == tile / 9 && p[j].col == tile % 9) {
        occupied = true;
        break;
      }
    ok = ok && (k == 8 ? occupied && h.dig
                       : !occupied && cooldowns[i * 8 + k] == 0 &&
                             h.sun >= PC[k] && (h.allowed & (1 << k)));
  }
  masks[ix] = ok;
}
