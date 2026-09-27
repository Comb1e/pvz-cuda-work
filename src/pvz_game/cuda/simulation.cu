// Sequential operations within each game deliberately retain Python insertion
// order. Parallelism is across independent games. All simulation arithmetic is
// signed int64.
typedef long long I;
__device__ I lo(I a, I b) { return a < b ? a : b; }
__device__ I hi(I a, I b) { return a > b ? a : b; }
__device__ I floor_div(I a, I b) { return a / b - (a % b < 0); }
struct Plant {
  I id, kind, row, col, health, state, due, burst_due;
};
struct Zombie {
  I id, kind, row, x, health, armor, state, slow_until, has_pole, vault_until,
      landing_x, bite_progress, move_remainder, target_id, previous_x, headless,
      age, speed, pole_speed, gait, gait_phase, phase_remainder, vault_start_x, vault_start_tick;
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
  __device__ void start_walk(Zombie &a, bool pole) {
    if (pole) {
      a.speed = a.pole_speed = random(ZP[a.kind], ZPMAX[a.kind]);
      a.gait = 2;
    } else {
      a.speed = a.kind == 1 ? ZS[a.kind] : random(ZS[a.kind], ZSMAX[a.kind]);
      I variant = random(0, 1);
      a.gait = a.kind == 4 ? 3 : (a.kind == 1 || variant == 0 ? 1 : 0);
    }
    a.gait_phase = a.phase_remainder = 0;
  }
  __device__ I gait_step(Zombie &a, bool slow) {
    I frames = GN[a.gait];
    I rate = a.speed * frames * M_animation_factor * M_phase_scale / (100 * GD[a.gait]);
    if (slow) rate /= 2;
    I index = a.gait_phase * (frames - 1) / M_phase_scale;
    I n = GDELTA[a.gait][index] * rate * G_units_per_tile + a.move_remainder;
    I distance = floor_div(n, M_move_denominator);
    a.move_remainder = n - distance * M_move_denominator;
    n = rate + a.phase_remainder;
    a.gait_phase = (a.gait_phase + n / (100 * frames)) % M_phase_scale;
    a.phase_remainder = n % (100 * frames);
    return distance;
  }
  __device__ bool contacts(Zombie &a, Plant &b, I end) {
    I offset = a.has_pole ? M_pole_attack_offset_pixels : M_attack_offset_pixels;
    I width = a.has_pole ? M_pole_attack_width_pixels : M_attack_width_pixels;
    I plant_left = (b.col * M_source_tile_pixels + M_plant_inset_pixels) * G_units_per_tile;
    I attack_left = end * M_source_tile_pixels + offset * G_units_per_tile;
    return lo(plant_left + M_plant_width_pixels * G_units_per_tile,
              attack_left + width * G_units_per_tile) - hi(plant_left, attack_left)
           >= M_contact_overlap_pixels * G_units_per_tile;
  }
  __device__ bool bite_immune(Plant &b) {
    return b.kind == 3 || (b.kind == 4 && b.state != 1);
  }
  __device__ bool projectile_contact(I zstart, I zend, I qstart, I qend) {
    I left = lo(zstart, zend) * M_source_tile_pixels;
    I right = hi(zstart, zend) * M_source_tile_pixels + M_body_width_pixels * G_units_per_tile;
    I qleft = lo(qstart, qend) * M_source_tile_pixels - M_projectile_back_pixels * G_units_per_tile;
    I qright = hi(qstart, qend) * M_source_tile_pixels + M_projectile_front_pixels * G_units_per_tile;
    return lo(right, qright) > hi(left, qleft);
  }
  __device__ bool mower_contact(I start, I end, I mower) {
    I left = lo(start, end) * M_source_tile_pixels;
    I right = hi(start, end) * M_source_tile_pixels + M_body_width_pixels * G_units_per_tile;
    I mower_left = mower * M_source_tile_pixels - M_mower_width_pixels * G_units_per_tile;
    return lo(right, mower * M_source_tile_pixels) > hi(left, mower_left);
  }
  __device__ I bite_target(Zombie &a, I x) {
    I best = -1;
    for (I i = 0; i < h->np; i++) {
      Plant &b = p[i];
      if (b.row == a.row && b.health > 0 && contacts(a, b, x) &&
          (best < 0 || b.col > p[best].col ||
           (b.col == p[best].col && b.id < p[best].id)))
        best = i;
    }
    return best;
  }
  __device__ I vault_target(Zombie &a, I x) {
    I best = -1;
    for (I i = 0; i < h->np; i++) {
      Plant &b = p[i];
      if (b.row == a.row && b.health > 0 && contacts(a, b, x) &&
          (best < 0 || b.col > p[best].col ||
           (b.col == p[best].col && b.id < p[best].id)))
        best = i;
    }
    return best;
  }
  __device__ I plant_target(Plant &a) {
    I best = -1;
    for (I i = 0; i < h->nz; i++) {
      Zombie &b = z[i];
      if (b.row != a.row || b.health <= 0 || b.state == 2) continue;
      I left = 60, right = 10000, extra = 0;
      if (a.kind == 4) {
        if (b.headless || b.gait == 2) continue;
        left = b.kind == 4 ? 40 : 0;
        right = 55;
        extra = b.state == 3 ? 30 : 0;
      } else if (a.kind == 6) {
        if (b.headless) continue;
        left = 80; right = 120;
        extra = b.state == 3 || a.state == 8 ? 60 : 0;
      }
      I origin = a.col * G_units_per_tile * 80;
      if (b.x * 80 <= origin + (right + extra) * G_units_per_tile &&
          b.x * 80 + 42 * G_units_per_tile >= origin + (left - extra) * G_units_per_tile &&
          (best < 0 || b.x < z[best].x || (b.x == z[best].x && b.id < z[best].id))) best = i;
    }
    return best;
  }
  __device__ I shot_target(I row, I start, I end) {
    I best = -1;
    for (I i = 0; i < h->nz; i++) {
      Zombie &a = z[i];
      if (a.health > 0 && a.row == row && a.state != 2 &&
          projectile_contact(a.x, a.x, start, end) &&
          (best < 0 || a.x < z[best].x || (a.x == z[best].x && a.id < z[best].id))) best = i;
    }
    return best;
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
    if (!a.headless && (a.health <= 0 || a.health < ZH[a.kind] / 3)) {
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
    I hit = 0;
    for (I j = 0; j < h->nz; j++) {
      I cx = a.col * G_units_per_tile * 80 + (rad ? 40 : 20) * G_units_per_tile;
      I cy = (a.row * 100 + 40) * G_units_per_tile;
      I dx = hi(hi(z[j].x * 80 - cx, 0), cx - z[j].x * 80 - 42 * G_units_per_tile);
      I dy = hi(hi((z[j].row * 100 - 30) * G_units_per_tile - cy, 0), cy - (z[j].row * 100 + 85) * G_units_per_tile);
      I radius = (rad ? M_cherry_radius_pixels : M_mine_radius_pixels) * G_units_per_tile;
      if ((rad || z[j].state != 2) && hi(z[j].row - a.row, a.row - z[j].row) <= rad && dx*dx+dy*dy <= radius*radius)
        hit += damage(j, PD[a.kind], a.id);
    }
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
            plant_target(a) >= 0)
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
        if (a.state == 2 && plant_target(a) >= 0) {
          detonate(i);
          continue;
        }
      } else if (kind == 6) {
        if (a.state == 8 && h->tick >= a.due) {
          I t = plant_target(a);
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
          I t = plant_target(a);
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
      I t = shot_target(a.row, a.x, end);
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
        if (q[j].row == a.row && a.state != 2 && projectile_contact(a.x, end, q[j].x, q[j].x) &&
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
        I elapsed = h->tick - a.vault_start_tick;
        a.x = a.vault_start_x - floor_div((a.vault_start_x - a.landing_x) * lo(elapsed * 24, 4300), 4300);
        if (h->tick < a.vault_until) continue;
        a.x -= M_jump_shift_pixels * G_units_per_tile / 80;
        a.state = 0;
        start_walk(a, false);
        emit(12, a.id);
      }
      // A pole carrier checks its attack rectangle before taking this tick's
      // walking step.  A target removed during flight does not cancel the jump.
      if (a.has_pole) {
        I pre = vault_target(a, a.x);
        if (pre >= 0) {
          Plant &b = p[pre];
          a.has_pole = 0;
          a.state = 2;
          a.vault_until = h->tick + (M_jump_frames * G_tick_rate + M_jump_fps - 1) / M_jump_fps;
          a.vault_start_tick = h->tick;
          a.vault_start_x = a.x;
          a.landing_x = b.col * G_units_per_tile + 116 * G_units_per_tile / 80;
          a.bite_progress = a.target_id = 0;
          emit(13, a.id, b.id);
          continue;
        }
      }
      bool slow = h->tick < a.slow_until;
      if (a.state != 3) move_z(i, a.x - gait_step(a, slow));
      // Both acquisition and release use age cadence; eating freezes movement.
      if (a.health <= 0 || a.headless || a.has_pole ||
          a.age % (G_bite_ticks * (slow ? 2 : 1)))
        continue;
      I best = bite_target(a, a.x);
      if (best < 0) {
        if (a.state == 3) start_walk(a, false);
        a.state = a.has_pole ? 1 : 0;
        a.bite_progress = a.target_id = 0;
        continue;
      }
      Plant &b = p[best];
      if (a.target_id != b.id) {
        a.bite_progress = 0;
        a.target_id = b.id;
      }
      a.state = 3;
      if (!bite_immune(b)) {
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
          if (z[i].health > 0 && !z[i].headless && z[i].row == r && mower_contact(z[i].previous_x, z[i].x, a.x)) {
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
            if (z[i].row == r && mower_contact(z[i].previous_x, z[i].x, a.x))
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
          if (z[i].row == r && z[i].health > 0 && z[i].x < end &&
              z[i].previous_x * 80 + 42 * G_units_per_tile > a.x * 80 - 50 * G_units_per_tile) {
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
      start_walk(z[h->nz - 1], k == 4);
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
