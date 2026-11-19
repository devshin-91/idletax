**English** | [한국어](how-it-works.ko.md)

# How IdleTax counts loss

## Subscriptions

### Price of one day

| How you pay | Price of one day |
|---|---|
| Every month | The month's price divided by the days in that month. 30,000 in November is 1,000 a day. |
| Once a year, renews every year | The year's price divided by the days in that paid year (365 or 366). A paid year runs from the start date to the same date a year later. |
| Once, for a fixed term | The amount divided by the days from start to end. |
| Installments, for a fixed term | The **total** divided by the days from start to end. 730,000 for 365 days is 2,000 a day. The monthly payment is not used, because skipping a day wastes a share of everything you agreed to pay. |

For installments you enter the total and the number of monthly installments. If you leave the end date empty, the term lasts as long as the installments (12 installments from November 2 end on November 1 a year later). If what you bought lasts longer than the payments, enter the end date. The list shows how many installments are paid and how much is left; payments are counted on the start day of each month.

### Missed days

You set a goal: how many days a week you mean to use it. Weeks run Monday to Sunday.

- A goal of 3 days leaves 4 days off. Days off cost nothing.
- Each unused day after those days off is a **missed day**. It is counted only once the goal can no longer be reached.
- A missed day loses that week's price divided by the goal. With 1,000 a day and a goal of 3, a missed day loses 7,000 ÷ 3 ≈ 2,333.
- So a week with no use at all loses exactly that week's price, and a week that meets the goal loses nothing.
- Today is never a missed day, because the day is not over.

Example, goal 3, nothing used all week: by Friday night only Saturday and Sunday are left, so one goal day is gone and Friday turns red. Saturday and Sunday follow.

### First and last weeks

If the term covers only part of a week, the goal shrinks in proportion (goal × days ÷ 7, rounded). A term that starts on Thursday has 4 days in its first week, so a goal of 3 becomes 2.

### Ending

- A monthly subscription that you end stops losing money after that day.
- A yearly subscription that you end keeps counting until the paid year runs out, then stops.
- A fixed-term item (paid once or in installments) ends on its end date. It cannot be ended early in the app, because the money is already committed.

### "Unused, 90 d"

Loss in the last 90 days divided by the price of those same days. 100% means you paid for 90 days and reached none of your goal. Items at 50% or more are shown in red.

## Decisions

```
cost per working day = people waiting × hourly cost per person × hours each loses per day
                       + other loss per day
loss                 = cost per working day × working days open
```

- Time counts from "waiting since" until now, or until the moment it was marked as decided.
- Only Monday to Friday count. Parts of a day count as fractions.
- Public holidays are not known to the app, so they count as working days.

## Periods and tabs

- **This week** starts on Monday, **this month** on the 1st, **this year** on January 1.
- A missed day belongs to the period that contains that day.
- The four cards show the loss for the tab that is open. The "All" tab adds every item.
- Tabs are yours to add, rename and remove. Removing a tab never deletes items: they move to "Uncategorized".
- Sample items count like any other item while they are loaded, and leave the totals when you remove the sample.
- Ended and decided items stay in the totals, because that money was lost too.

## What the numbers are not

Use days and costs are your own entries. The app does not measure usage or anyone's time.
Use the numbers to compare items and decide what to cancel or settle, not as accounting figures.

The tests in `test_core.py` check each rule on this page.
