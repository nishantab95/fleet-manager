import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'data/api_client.dart';
import 'domain/role_models.dart';
import 'fleet_theme.dart';
import 'owner_fleet.dart';
import 'owner_people_sites.dart';

typedef SignOut = Future<void> Function();

class SupervisorHomeScreen extends StatefulWidget {
  const SupervisorHomeScreen({
    required this.api,
    required this.onSignOut,
    super.key,
  });

  final ApiClient api;
  final SignOut onSignOut;

  @override
  State<SupervisorHomeScreen> createState() => _SupervisorHomeScreenState();
}

class _SupervisorHomeScreenState extends State<SupervisorHomeScreen> {
  List<SupervisorSite> _sites = const [];
  Map<String, List<SupervisorEvent>> _eventsBySite = const {};
  String? _selectedSiteId;
  String _supervisorName = 'Supervisor';
  bool _loading = true;
  bool _offline = false;
  String? _error;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(const Duration(seconds: 30), (_) => _load());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final supervisorName = await widget.api.currentDisplayName();
      final sites = await widget.api.supervisorSites();
      final siteData = await Future.wait(
        sites.map(
          (site) async => (
            siteId: site.id,
            events: await widget.api.supervisorEvents(site.id),
          ),
        ),
      );
      if (!mounted) return;
      setState(() {
        _sites = sites;
        _supervisorName = supervisorName;
        _eventsBySite = {for (final item in siteData) item.siteId: item.events};
        if (!sites.any((site) => site.id == _selectedSiteId)) {
          _selectedSiteId = sites.firstOrNull?.id;
        }
        _error = null;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      if (!mounted) return;
      setState(() {
        _offline = error.isRetryable;
        _error = _friendlyError(error);
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _replaceSiteEvents(String siteId, List<SupervisorEvent> events) {
    if (!mounted) return;
    setState(() {
      _eventsBySite = {..._eventsBySite, siteId: events};
    });
  }

  Future<void> _openCategory(_SupervisorReviewCategory category) async {
    final site = _sites.where((item) => item.id == _selectedSiteId).firstOrNull;
    if (site == null) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => _SupervisorCategoryScreen(
          api: widget.api,
          onSignOut: widget.onSignOut,
          site: site,
          category: category,
          initialEvents: _eventsBySite[site.id] ?? const [],
          onEventsChanged: (events) => _replaceSiteEvents(site.id, events),
        ),
      ),
    );
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final selectedSite = _sites
        .where((site) => site.id == _selectedSiteId)
        .firstOrNull;
    final selectedEvents = selectedSite == null
        ? const <SupervisorEvent>[]
        : _eventsBySite[selectedSite.id] ?? const <SupervisorEvent>[];
    final counts = _SupervisorCategoryCounts.fromEvents(selectedEvents);
    final siteLabel = selectedSite?.shortName?.trim().isNotEmpty == true
        ? selectedSite!.shortName!
        : selectedSite?.name ?? 'No assigned site';
    return _RoleScaffold(
      title: _supervisorName,
      subtitle: siteLabel,
      onRefresh: _load,
      onSignOut: widget.onSignOut,
      offline: _offline,
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          key: const Key('supervisor-scroll'),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            if (_error != null) _ErrorBanner(message: _error!, onRetry: _load),
            if (_loading && _eventsBySite.isEmpty)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(28),
                  child: CircularProgressIndicator(),
                ),
              ),
            if (_sites.length > 1)
              DropdownButtonFormField<String>(
                key: const Key('supervisor-site-selector'),
                initialValue: selectedSite?.id,
                decoration: const InputDecoration(
                  labelText: 'Current Site',
                  prefixIcon: Icon(Icons.location_on_outlined),
                ),
                items: [
                  for (final site in _sites)
                    DropdownMenuItem(
                      value: site.id,
                      child: Text(site.shortName ?? site.name),
                    ),
                ],
                onChanged: (value) => setState(() {
                  _selectedSiteId = value;
                }),
              ),
            if (_sites.length > 1) const SizedBox(height: 12),
            _SupervisorAttentionGrid(counts: counts, onOpen: _openCategory),
            const SizedBox(height: 12),
            _SupervisorPendingNotifications(
              counts: counts,
              onOpen: _openCategory,
            ),
          ],
        ),
      ),
    );
  }
}

enum _SupervisorReviewCategory { emergency, diesel, trips, meter }

extension on _SupervisorReviewCategory {
  String get title => switch (this) {
    _SupervisorReviewCategory.emergency => 'Emergencies',
    _SupervisorReviewCategory.diesel => 'Diesel',
    _SupervisorReviewCategory.trips => 'Trips',
    _SupervisorReviewCategory.meter => 'Meter readings',
  };

  String get notificationLabel => switch (this) {
    _SupervisorReviewCategory.emergency => 'Emergency',
    _SupervisorReviewCategory.diesel => 'Diesel',
    _SupervisorReviewCategory.trips => 'Trips',
    _SupervisorReviewCategory.meter => 'Meter',
  };

  bool matches(SupervisorEvent event) => switch (this) {
    _SupervisorReviewCategory.emergency => event.isEmergency,
    _SupervisorReviewCategory.diesel => event.isDiesel,
    _SupervisorReviewCategory.trips =>
      event.isTrip && event.assetType == 'TIPPER',
    _SupervisorReviewCategory.meter =>
      (event.assetType == 'TIPPER' && event.isKm) ||
          (event.assetType != 'TIPPER' && event.isHmr),
  };

  bool isPending(SupervisorEvent event) => switch (this) {
    _SupervisorReviewCategory.emergency => event.isOpenEmergency,
    _ => event.isPending,
  };

  String get emptyPending => switch (this) {
    _SupervisorReviewCategory.emergency => 'No open emergencies.',
    _ => 'Nothing pending.',
  };
}

class _SupervisorCategoryCounts {
  const _SupervisorCategoryCounts({
    required this.emergency,
    required this.diesel,
    required this.trips,
    required this.meter,
  });

  factory _SupervisorCategoryCounts.fromEvents(
    Iterable<SupervisorEvent> events,
  ) {
    int count(_SupervisorReviewCategory category) => events
        .where((event) => category.matches(event) && category.isPending(event))
        .length;
    return _SupervisorCategoryCounts(
      emergency: count(_SupervisorReviewCategory.emergency),
      diesel: count(_SupervisorReviewCategory.diesel),
      trips: count(_SupervisorReviewCategory.trips),
      meter: count(_SupervisorReviewCategory.meter),
    );
  }

  final int emergency;
  final int diesel;
  final int trips;
  final int meter;

  int get total => emergency + diesel + trips + meter;

  int forCategory(_SupervisorReviewCategory category) => switch (category) {
    _SupervisorReviewCategory.emergency => emergency,
    _SupervisorReviewCategory.diesel => diesel,
    _SupervisorReviewCategory.trips => trips,
    _SupervisorReviewCategory.meter => meter,
  };
}

enum _SupervisorCategoryTab { pending, history }

class _SupervisorCategoryScreen extends StatefulWidget {
  const _SupervisorCategoryScreen({
    required this.api,
    required this.onSignOut,
    required this.site,
    required this.category,
    required this.initialEvents,
    required this.onEventsChanged,
  });

  final ApiClient api;
  final SignOut onSignOut;
  final SupervisorSite site;
  final _SupervisorReviewCategory category;
  final List<SupervisorEvent> initialEvents;
  final ValueChanged<List<SupervisorEvent>> onEventsChanged;

  @override
  State<_SupervisorCategoryScreen> createState() =>
      _SupervisorCategoryScreenState();
}

class _SupervisorCategoryScreenState extends State<_SupervisorCategoryScreen> {
  late List<SupervisorEvent> _events = [...widget.initialEvents];
  _SupervisorCategoryTab _tab = _SupervisorCategoryTab.pending;
  bool _loading = false;
  bool _offline = false;
  String? _error;
  String? _message;

  List<SupervisorEvent> get _categoryEvents =>
      _events.where(widget.category.matches).toList();

  List<SupervisorEvent> get _pending =>
      _categoryEvents.where(widget.category.isPending).toList()..sort(
        (a, b) => (a.deviceCreatedAt ?? DateTime(1970)).compareTo(
          b.deviceCreatedAt ?? DateTime(1970),
        ),
      );

  List<SupervisorEvent> get _history =>
      _categoryEvents
          .where((event) => !widget.category.isPending(event))
          .toList()
        ..sort(
          (a, b) => (b.deviceCreatedAt ?? DateTime(1970)).compareTo(
            a.deviceCreatedAt ?? DateTime(1970),
          ),
        );

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final events = await widget.api.supervisorEvents(widget.site.id);
      if (!mounted) return;
      setState(() {
        _events = events;
        _error = null;
        _offline = false;
      });
      widget.onEventsChanged(events);
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      if (mounted) {
        setState(() {
          _offline = error.isRetryable;
          _error = _friendlyError(error);
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _replaceEvent(SupervisorEvent updated, String message) {
    setState(() {
      _events = _events
          .map((event) => event.id == updated.id ? updated : event)
          .toList();
      _message = message;
      _error = null;
    });
    widget.onEventsChanged(_events);
  }

  Future<void> _verify(SupervisorEvent event, String decision) async {
    String? reason;
    if (decision != 'APPROVED') reason = await _askReason(decision);
    if (decision != 'APPROVED' && reason == null) return;
    try {
      final updated = await widget.api.verifySupervisorEvent(
        event.id,
        decision: decision,
        reason: reason,
      );
      if (!mounted) return;
      _replaceEvent(
        updated,
        decision == 'APPROVED'
            ? 'Record approved.'
            : 'Record marked $decision.',
      );
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = _friendlyError(error));
    }
  }

  Future<String?> _askReason(String decision) async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          decision == 'REJECTED' ? 'Reject record' : 'Dispute record',
        ),
        content: TextField(
          controller: controller,
          maxLines: 3,
          decoration: const InputDecoration(labelText: 'Reason'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('SUBMIT'),
          ),
        ],
      ),
    );
    controller.dispose();
    return result?.isEmpty == true ? null : result;
  }

  Future<void> _emergencyAction(SupervisorEvent event, String action) async {
    try {
      final updated = action == 'acknowledge'
          ? await widget.api.acknowledgeEmergency(event.id)
          : await widget.api.resolveEmergency(event.id);
      if (!mounted) return;
      _replaceEvent(
        updated,
        action == 'acknowledge'
            ? 'Emergency acknowledged.'
            : 'Emergency resolved.',
      );
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = _friendlyError(error));
    }
  }

  Future<void> _call(String? phone) async {
    if (phone == null || phone.isEmpty) return;
    final uri = Uri(scheme: 'tel', path: phone);
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) &&
        mounted) {
      setState(() => _error = 'Unable to open the phone dialer.');
    }
  }

  Future<void> _showEvidence(SupervisorEvent event) async {
    if (!event.evidenceAvailable) return;
    showDialog<void>(
      context: context,
      builder: (context) => _EvidenceDialog(
        title: '${event.eventType} · ${event.tipperRegistration}',
        loader: () => widget.api.evidenceBytes(event.id, role: 'SUPERVISOR'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pending = _pending;
    final history = _history;
    final visible = _tab == _SupervisorCategoryTab.pending ? pending : history;
    final siteLabel = widget.site.shortName?.trim().isNotEmpty == true
        ? widget.site.shortName!
        : widget.site.name;
    return _RoleScaffold(
      title: widget.category.title,
      subtitle: siteLabel,
      onRefresh: _load,
      onSignOut: widget.onSignOut,
      offline: _offline,
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          key: Key('supervisor-category-${widget.category.name}'),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            if (_error != null) _ErrorBanner(message: _error!, onRetry: _load),
            if (_message != null) _MessageBanner(message: _message!),
            Row(
              children: [
                Expanded(
                  child: Text(
                    widget.category == _SupervisorReviewCategory.emergency
                        ? 'Pending / Open: ${pending.length}'
                        : 'Pending: ${pending.length}',
                    key: const Key('supervisor-category-pending-count'),
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (_loading)
                  const SizedBox.square(
                    dimension: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            const SizedBox(height: FleetSpacing.sm),
            SegmentedButton<_SupervisorCategoryTab>(
              key: const Key('supervisor-category-tabs'),
              segments: [
                ButtonSegment(
                  value: _SupervisorCategoryTab.pending,
                  label: Text('PENDING ${pending.length}'),
                ),
                const ButtonSegment(
                  value: _SupervisorCategoryTab.history,
                  label: Text('HISTORY'),
                ),
              ],
              selected: {_tab},
              onSelectionChanged: (selection) =>
                  setState(() => _tab = selection.first),
            ),
            const SizedBox(height: FleetSpacing.md),
            if (visible.isEmpty)
              _EmptyCard(
                icon: _tab == _SupervisorCategoryTab.pending
                    ? Icons.check_circle_outline
                    : Icons.history,
                text: _tab == _SupervisorCategoryTab.pending
                    ? widget.category.emptyPending
                    : 'No ${widget.category.notificationLabel.toLowerCase()} history.',
              ),
            for (final event in visible)
              if (event.isEmergency && _tab == _SupervisorCategoryTab.pending)
                _EmergencyCard(
                  event: event,
                  showSite: false,
                  onCall: () => _call(event.driverPhone),
                  onAcknowledge: () => _emergencyAction(event, 'acknowledge'),
                  onResolve: () => _emergencyAction(event, 'resolve'),
                )
              else
                _ReviewEventCard(
                  event: event,
                  showReviewActions:
                      _tab == _SupervisorCategoryTab.pending &&
                      !event.isEmergency,
                  onVerify: _verify,
                  onCall: _call,
                  onEvidence: _showEvidence,
                ),
          ],
        ),
      ),
    );
  }
}

class _SupervisorAttentionGrid extends StatelessWidget {
  const _SupervisorAttentionGrid({required this.counts, required this.onOpen});

  final _SupervisorCategoryCounts counts;
  final ValueChanged<_SupervisorReviewCategory> onOpen;

  @override
  Widget build(BuildContext context) => GridView.count(
    key: const Key('supervisor-attention-grid'),
    crossAxisCount: 2,
    crossAxisSpacing: FleetSpacing.sm,
    mainAxisSpacing: FleetSpacing.sm,
    childAspectRatio: 1.5,
    shrinkWrap: true,
    physics: const NeverScrollableScrollPhysics(),
    children: [
      _SupervisorAttentionTile(
        key: const Key('supervisor-tile-emergency'),
        countKey: const Key('supervisor-count-emergency'),
        label: 'EMERGENCIES',
        count: counts.emergency,
        icon: Icons.warning_amber_rounded,
        accent: FleetColors.danger,
        onTap: () => onOpen(_SupervisorReviewCategory.emergency),
      ),
      _SupervisorAttentionTile(
        key: const Key('supervisor-tile-diesel'),
        countKey: const Key('supervisor-count-diesel'),
        label: 'DIESEL APPROVALS',
        count: counts.diesel,
        icon: Icons.local_gas_station_outlined,
        accent: FleetColors.amber,
        onTap: () => onOpen(_SupervisorReviewCategory.diesel),
      ),
      _SupervisorAttentionTile(
        key: const Key('supervisor-tile-trips'),
        countKey: const Key('supervisor-count-trips'),
        label: 'TRIP APPROVALS',
        count: counts.trips,
        icon: Icons.route_outlined,
        accent: FleetColors.deepGreen,
        onTap: () => onOpen(_SupervisorReviewCategory.trips),
      ),
      _SupervisorAttentionTile(
        key: const Key('supervisor-tile-meter'),
        countKey: const Key('supervisor-count-meter'),
        label: 'METER READINGS',
        count: counts.meter,
        icon: Icons.speed_outlined,
        accent: FleetColors.steel,
        onTap: () => onOpen(_SupervisorReviewCategory.meter),
      ),
    ],
  );
}

class _SupervisorAttentionTile extends StatelessWidget {
  const _SupervisorAttentionTile({
    required super.key,
    required this.countKey,
    required this.label,
    required this.count,
    required this.icon,
    required this.accent,
    required this.onTap,
  });

  final Key countKey;
  final String label;
  final int count;
  final IconData icon;
  final Color accent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: '$label, $count pending',
    child: Material(
      color: count > 0
          ? accent.withValues(alpha: 0.11)
          : Theme.of(context).colorScheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(FleetRadius.md),
        side: BorderSide(color: count > 0 ? accent : FleetColors.outline),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(FleetSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Row(
                children: [
                  Icon(icon, color: accent),
                  const Spacer(),
                  Text(
                    '$count',
                    key: countKey,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      color: count > 0 ? accent : FleetColors.muted,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: FleetSpacing.sm),
              Text(
                label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  color: count > 0 ? FleetColors.ink : FleetColors.muted,
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _SupervisorPendingNotifications extends StatelessWidget {
  const _SupervisorPendingNotifications({
    required this.counts,
    required this.onOpen,
  });

  final _SupervisorCategoryCounts counts;
  final ValueChanged<_SupervisorReviewCategory> onOpen;

  @override
  Widget build(BuildContext context) => Card(
    key: const Key('supervisor-pending-notifications'),
    child: Padding(
      padding: const EdgeInsets.all(FleetSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Pending notifications',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              Text(
                '${counts.total}',
                key: const Key('supervisor-pending-total'),
                style: Theme.of(
                  context,
                ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
              ),
            ],
          ),
          if (counts.total == 0) ...[
            const SizedBox(height: FleetSpacing.sm),
            const Text('Nothing requires your attention.'),
          ] else
            for (final category in _SupervisorReviewCategory.values)
              if (counts.forCategory(category) > 0)
                ListTile(
                  key: Key('supervisor-notification-${category.name}'),
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(category.notificationLabel),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text('${counts.forCategory(category)}'),
                      const Icon(Icons.chevron_right),
                    ],
                  ),
                  onTap: () => onOpen(category),
                ),
        ],
      ),
    ),
  );
}

class _ReviewEventCard extends StatelessWidget {
  const _ReviewEventCard({
    required this.event,
    required this.showReviewActions,
    required this.onVerify,
    required this.onCall,
    required this.onEvidence,
  });

  final SupervisorEvent event;
  final bool showReviewActions;
  final Future<void> Function(SupervisorEvent event, String decision) onVerify;
  final Future<void> Function(String? phone) onCall;
  final Future<void> Function(SupervisorEvent event) onEvidence;

  @override
  Widget build(BuildContext context) {
    final assetLabel = event.assetShortName?.trim().isNotEmpty == true
        ? event.assetShortName!
        : event.assetCode?.trim().isNotEmpty == true
        ? event.assetCode!
        : event.tipperRegistration;
    final detail = event.isHmr
        ? '${event.readingType == 'START_READING' ? 'START' : 'END'} HMR · ${_numberText(event.readingValue)} hours'
        : event.isKm
        ? '${event.readingType == 'START_READING' ? 'START' : 'END'} ODOMETER · ${_numberText(event.readingValue)} KM'
        : event.isDiesel
        ? '${_numberText(event.litres)} LITRES'
        : event.isTrip
        ? 'Trip Complete'
        : '${event.emergencyCategory ?? 'Emergency'} · ${event.emergencyStatus ?? ''}';
    return Card(
      key: Key('supervisor-event-${event.id}'),
      margin: const EdgeInsets.fromLTRB(12, 0, 12, 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: FleetSpacing.sm,
              runSpacing: FleetSpacing.xs,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  detail,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                _StatusChip(event.verificationStatus),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              assetLabel,
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            if (event.tipperRegistration.isNotEmpty &&
                event.tipperRegistration != assetLabel)
              Text(event.tipperRegistration),
            Text('${event.driverName} · ${_formatDate(event.deviceCreatedAt)}'),
            if (event.isDiesel && !event.evidenceAvailable)
              Text(
                'Evidence not provided',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            if (event.isDiesel && event.evidenceAvailable)
              Text(
                'Evidence attached',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                if (event.evidenceAvailable)
                  TextButton.icon(
                    onPressed: () => onEvidence(event),
                    icon: const Icon(Icons.photo_outlined),
                    label: const Text('VIEW PHOTO'),
                  ),
                if (event.isEmergency && event.driverPhone != null)
                  TextButton.icon(
                    onPressed: () => onCall(event.driverPhone),
                    icon: const Icon(Icons.call_outlined),
                    label: const Text('CALL DRIVER'),
                  ),
                if (showReviewActions &&
                    event.isPending &&
                    !event.isEmergency) ...[
                  TextButton(
                    onPressed: () => onVerify(event, 'APPROVED'),
                    child: const Text('APPROVE'),
                  ),
                  TextButton(
                    onPressed: () => onVerify(event, 'REJECTED'),
                    child: const Text('REJECT'),
                  ),
                  TextButton(
                    onPressed: () => onVerify(event, 'DISPUTED'),
                    child: const Text('DISPUTE'),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class OwnerHomeScreen extends StatefulWidget {
  const OwnerHomeScreen({
    required this.api,
    required this.onSignOut,
    super.key,
  });

  final ApiClient api;
  final SignOut onSignOut;

  @override
  State<OwnerHomeScreen> createState() => _OwnerHomeScreenState();
}

class _OwnerHomeScreenState extends State<OwnerHomeScreen> {
  OwnerDashboard? _dashboard;
  List<OwnerTipperReport> _tippers = const [];
  List<OwnerDutyReport> _duties = const [];
  List<SupervisorEvent> _alerts = const [];
  int _tab = 0;
  bool _loading = true;
  bool _offline = false;
  String? _error;
  DateTime _date = DateTime.now();
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(const Duration(seconds: 60), (_) => _load());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    try {
      final dashboard = await widget.api.ownerDashboard(date: _date);
      final siteReports = await Future.wait(
        dashboard.sites.map(
          (site) => widget.api.ownerSiteDaily(site.id, date: _date),
        ),
      );
      final tippers = siteReports.expand((items) => items).toList();
      final alerts =
          tippers
              .expand((item) => item.events)
              .where((event) => event.isEmergency || event.isPending)
              .toList()
            ..sort(
              (a, b) => (b.deviceCreatedAt ?? DateTime(1970)).compareTo(
                a.deviceCreatedAt ?? DateTime(1970),
              ),
            );
      final duties = await widget.api.ownerDuty(date: _date);
      if (!mounted) return;
      setState(() {
        _dashboard = dashboard;
        _tippers = tippers;
        _alerts = alerts;
        _duties = duties;
        _offline = false;
        _error = null;
      });
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onSignOut();
        return;
      }
      if (mounted) {
        setState(() {
          _offline = error.isRetryable;
          _error = _friendlyError(error);
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      initialDate: _date,
    );
    if (picked != null) {
      setState(() => _date = picked);
      await _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final titles = [
      'Owner dashboard',
      'Fleet',
      'People',
      'Tippers',
      'Sites',
      'Alerts',
      'Reports',
    ];
    return _RoleScaffold(
      title: titles[_tab],
      subtitle: 'TODAY · ${_date.toIso8601String().substring(0, 10)}',
      onRefresh: _load,
      onSignOut: widget.onSignOut,
      offline: _offline,
      body: IndexedStack(
        index: _tab,
        children: [
          _OwnerDashboardBody(
            dashboard: _dashboard,
            duties: _duties,
            loading: _loading,
            error: _error,
            onRetry: _load,
          ),
          OwnerFleetScreen(api: widget.api, onUnauthorized: widget.onSignOut),
          OwnerPeopleScreen(api: widget.api, onUnauthorized: widget.onSignOut),
          _OwnerTippersBody(tippers: _tippers, onEvidence: _showEvidence),
          OwnerSitesScreen(
            api: widget.api,
            assetApi: widget.api,
            onUnauthorized: widget.onSignOut,
          ),
          _OwnerAlertsBody(alerts: _alerts, onEvidence: _showEvidence),
          if (_tab == 6)
            _OwnerReportsBody(
              api: widget.api,
              date: _date,
              duties: _duties,
              onPickDate: _pickDate,
              onExport: _export,
              onUnauthorized: widget.onSignOut,
            )
          else
            const SizedBox.shrink(),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        labelBehavior: NavigationDestinationLabelBehavior.onlyShowSelected,
        onDestinationSelected: (value) => setState(() => _tab = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'HOME',
          ),
          NavigationDestination(
            icon: Icon(Icons.local_shipping_outlined),
            label: 'FLEET',
          ),
          NavigationDestination(
            icon: Icon(Icons.people_outline),
            label: 'PEOPLE',
          ),
          NavigationDestination(
            icon: Icon(Icons.list_alt_outlined),
            label: 'TIPPERS',
          ),
          NavigationDestination(
            icon: Icon(Icons.location_on_outlined),
            label: 'SITES',
          ),
          NavigationDestination(
            icon: Icon(Icons.warning_amber_outlined),
            label: 'ALERTS',
          ),
          NavigationDestination(
            icon: Icon(Icons.assessment_outlined),
            label: 'REPORTS',
          ),
        ],
      ),
    );
  }

  Future<void> _showEvidence(SupervisorEvent event) async {
    if (!event.evidenceAvailable) return;
    showDialog<void>(
      context: context,
      builder: (context) => _EvidenceDialog(
        title: '${event.eventType} · ${event.tipperRegistration}',
        loader: () => widget.api.evidenceBytes(event.id, role: 'OWNER_ADMIN'),
      ),
    );
  }

  Future<void> _export(ReportTemplate template) async {
    try {
      final bytes = await widget.api.dailyExcel(
        date: _date,
        templateId: template.id,
      );
      final directory = await getTemporaryDirectory();
      final templateSegment = template.name
          .trim()
          .replaceAll(RegExp(r'[^A-Za-z0-9]+'), '-')
          .replaceAll(RegExp(r'^-+|-+$'), '');
      final path =
          '${directory.path}${Platform.pathSeparator}FleetManager-${_date.toIso8601String().substring(0, 10)}-$templateSegment.xlsx';
      await File(path).writeAsBytes(bytes, flush: true);
      final file = XFile(
        path,
        mimeType:
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      );
      await Share.shareXFiles([file], text: 'Fleet Manager report');
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = _friendlyError(error));
    } on Object catch (error) {
      if (mounted) {
        setState(() => _error = 'Could not share the report: $error');
      }
    }
  }
}

class _OwnerDashboardBody extends StatelessWidget {
  const _OwnerDashboardBody({
    required this.dashboard,
    required this.duties,
    required this.loading,
    required this.error,
    required this.onRetry,
  });

  final OwnerDashboard? dashboard;
  final List<OwnerDutyReport> duties;
  final bool loading;
  final String? error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    if (loading && dashboard == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (dashboard == null) {
      return _ErrorBanner(
        message: error ?? 'No report loaded.',
        onRetry: onRetry,
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        if (error != null) _ErrorBanner(message: error!, onRetry: onRetry),
        Text('TODAY', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        _MetricGrid(
          metrics: [
            _Metric(
              'ACTIVE TIPPERS',
              '${dashboard!.activeTippers}',
              Icons.local_shipping_outlined,
            ),
            _Metric(
              'APPROVED TRIPS',
              '${dashboard!.approvedTrips}',
              Icons.check_circle_outline,
            ),
            _Metric(
              'DISTANCE',
              '${_numberText(dashboard!.distanceKm)} KM',
              Icons.route_outlined,
            ),
            _Metric(
              'DIESEL ISSUED',
              '${_numberText(dashboard!.dieselIssued)} L',
              Icons.local_gas_station_outlined,
            ),
          ],
        ),
        const SizedBox(height: 20),
        Text('ATTENTION', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 10),
        _MetricGrid(
          metrics: [
            _Metric(
              'PENDING',
              '${dashboard!.pending}',
              Icons.pending_actions_outlined,
              danger: dashboard!.pending > 0,
            ),
            _Metric(
              'MISSING KM',
              '${dashboard!.missingReadings}',
              Icons.speed_outlined,
              danger: dashboard!.missingReadings > 0,
            ),
            _Metric(
              'OPEN EMERGENCIES',
              '${dashboard!.openEmergencies}',
              Icons.warning_amber_outlined,
              danger: dashboard!.openEmergencies > 0,
            ),
            _Metric(
              'PAST REGULAR DUTY',
              '${dashboard!.driversPastDuty}',
              Icons.schedule_outlined,
              danger: dashboard!.driversPastDuty > 0,
            ),
          ],
        ),
        const SizedBox(height: 20),
        Text('DUTY MONITOR', style: Theme.of(context).textTheme.titleLarge),
        for (final duty in duties.take(5)) _DutyCard(duty: duty),
      ],
    );
  }
}

class _OwnerTippersBody extends StatelessWidget {
  const _OwnerTippersBody({required this.tippers, required this.onEvidence});

  final List<OwnerTipperReport> tippers;
  final Future<void> Function(SupervisorEvent) onEvidence;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      if (tippers.isEmpty)
        const _EmptyCard(
          icon: Icons.local_shipping_outlined,
          text: 'No tippers in this report day.',
        ),
      for (final tipper in tippers)
        Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: ExpansionTile(
            title: Text(
              tipper.shortName ?? tipper.registration,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            subtitle: Text('${tipper.registration} · ${tipper.siteName}'),
            children: [
              ListTile(
                leading: const Icon(Icons.person_outline),
                title: const Text('Driver'),
                subtitle: Text(tipper.driverName),
              ),
              _KeyValueRow('Approved trips', '${tipper.approvedTrips}'),
              _KeyValueRow('Distance', '${_numberText(tipper.distanceKm)} KM'),
              _KeyValueRow('Diesel issued', '${_numberText(tipper.diesel)} L'),
              _KeyValueRow(
                'Completeness',
                tipper.missingStart || tipper.missingEnd
                    ? 'Missing KM'
                    : 'Complete',
              ),
              if (tipper.events.isNotEmpty)
                for (final event in tipper.events.take(8))
                  ListTile(
                    dense: true,
                    title: Text(event.eventType),
                    subtitle: Text(
                      '${_formatDate(event.deviceCreatedAt)} · ${event.verificationStatus}',
                    ),
                    trailing: event.evidenceAvailable
                        ? IconButton(
                            icon: const Icon(Icons.photo_outlined),
                            onPressed: () => onEvidence(event),
                          )
                        : null,
                  ),
            ],
          ),
        ),
    ],
  );
}

class _OwnerAlertsBody extends StatelessWidget {
  const _OwnerAlertsBody({required this.alerts, required this.onEvidence});
  final List<SupervisorEvent> alerts;
  final Future<void> Function(SupervisorEvent) onEvidence;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      if (alerts.isEmpty)
        const _EmptyCard(
          icon: Icons.check_circle_outline,
          text: 'No operational attention items.',
        ),
      for (final event in alerts)
        Card(
          color: event.isEmergency
              ? Theme.of(context).colorScheme.errorContainer
              : null,
          child: ListTile(
            leading: Icon(
              event.isEmergency ? Icons.warning_amber : Icons.pending_actions,
            ),
            title: Text(
              event.isEmergency
                  ? 'EMERGENCY · ${event.emergencyStatus ?? ''}'
                  : event.eventType,
            ),
            subtitle: Text(
              '${event.driverName} · ${event.tipperRegistration}\n${event.siteName} · ${_formatDate(event.deviceCreatedAt)}',
            ),
            isThreeLine: true,
            trailing: event.evidenceAvailable
                ? IconButton(
                    icon: const Icon(Icons.photo_outlined),
                    onPressed: () => onEvidence(event),
                  )
                : null,
          ),
        ),
    ],
  );
}

class _OwnerReportsBody extends StatefulWidget {
  const _OwnerReportsBody({
    required this.api,
    required this.date,
    required this.duties,
    required this.onPickDate,
    required this.onExport,
    required this.onUnauthorized,
  });
  final ApiClient api;
  final DateTime date;
  final List<OwnerDutyReport> duties;
  final Future<void> Function() onPickDate;
  final Future<void> Function(ReportTemplate template) onExport;
  final SignOut onUnauthorized;

  @override
  State<_OwnerReportsBody> createState() => _OwnerReportsBodyState();
}

class _OwnerReportsBodyState extends State<_OwnerReportsBody> {
  List<ReportTemplate> _templates = const [];
  String? _selectedTemplateId;
  bool _loading = true;
  String? _error;

  ReportTemplate? get _selectedTemplate {
    for (final template in _templates) {
      if (template.id == _selectedTemplateId) return template;
    }
    return null;
  }

  @override
  void initState() {
    super.initState();
    _loadTemplates();
  }

  Future<void> _loadTemplates() async {
    if (mounted) setState(() => _loading = true);
    try {
      final templates = await widget.api.reportTemplates();
      if (!mounted) return;
      final retained = templates.any((item) => item.id == _selectedTemplateId)
          ? _selectedTemplateId
          : null;
      setState(() {
        _templates = templates;
        _selectedTemplateId = retained ?? _preferredTemplateId(templates);
        _error = null;
      });
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onUnauthorized();
        return;
      }
      if (mounted) setState(() => _error = _friendlyError(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _mutate(Future<void> Function() action) async {
    try {
      await action();
      await _loadTemplates();
    } on ApiException catch (error) {
      if (error.isUnauthorized) {
        await widget.onUnauthorized();
        return;
      }
      if (mounted) setState(() => _error = _friendlyError(error));
    }
  }

  Future<void> _createOrEdit([ReportTemplate? existing]) async {
    final seed = existing ?? _selectedTemplate;
    if (seed == null) return;
    final input = await _showReportTemplateDialog(
      context,
      existing: existing,
      seed: seed,
    );
    if (input == null) return;
    await _mutate(() async {
      final saved = existing == null
          ? await widget.api.createReportTemplate(input)
          : await widget.api.updateReportTemplate(existing.id, input);
      _selectedTemplateId = saved.id;
    });
  }

  Future<void> _duplicate(ReportTemplate template) async {
    final name = await _showTemplateNameDialog(
      context,
      title: 'Duplicate template',
      initialName: '${template.name} Copy',
    );
    if (name == null) return;
    await _mutate(() async {
      final saved = await widget.api.duplicateReportTemplate(template.id, name);
      _selectedTemplateId = saved.id;
    });
  }

  Future<void> _delete(ReportTemplate template) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete report template?'),
        content: Text('${template.name} will be permanently removed.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('DELETE'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _mutate(() => widget.api.deleteReportTemplate(template.id));
  }

  Future<void> _templateAction(ReportTemplate template, String action) async {
    switch (action) {
      case 'edit':
        await _createOrEdit(template);
        return;
      case 'duplicate':
        await _duplicate(template);
        return;
      case 'default':
        await _mutate(() async {
          await widget.api.setDefaultReportTemplate(template.id);
          _selectedTemplateId = template.id;
        });
        return;
      case 'delete':
        await _delete(template);
        return;
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
    children: [
      Row(
        children: [
          Expanded(
            child: Text(
              'Reports · ${widget.date.toIso8601String().substring(0, 10)}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          IconButton(
            onPressed: widget.onPickDate,
            icon: const Icon(Icons.calendar_today_outlined),
          ),
        ],
      ),
      if (_error != null) ...[
        _ErrorBanner(message: _error!, onRetry: _loadTemplates),
        const SizedBox(height: 8),
      ],
      if (_loading)
        const LinearProgressIndicator()
      else if (_templates.isNotEmpty)
        DropdownButtonFormField<String>(
          key: const Key('report-template-selector'),
          initialValue: _selectedTemplateId,
          decoration: const InputDecoration(
            labelText: 'Report template',
            border: OutlineInputBorder(),
          ),
          items: [
            for (final template in _templates)
              DropdownMenuItem(
                value: template.id,
                child: Text(
                  '${template.name}${template.isDefault ? ' · DEFAULT' : ''}',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
          onChanged: (value) => setState(() => _selectedTemplateId = value),
        ),
      const SizedBox(height: 10),
      FilledButton.icon(
        key: const Key('export-template-excel'),
        onPressed: _selectedTemplate == null
            ? null
            : () => widget.onExport(_selectedTemplate!),
        icon: const Icon(Icons.ios_share_outlined),
        label: const Text('EXPORT EXCEL'),
      ),
      const SizedBox(height: 20),
      Row(
        children: [
          Expanded(
            child: Text(
              'REPORT TEMPLATES',
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          FilledButton.tonalIcon(
            key: const Key('new-report-template'),
            onPressed: _templates.isEmpty ? null : _createOrEdit,
            icon: const Icon(Icons.add),
            label: const Text('NEW'),
          ),
        ],
      ),
      const SizedBox(height: 8),
      for (final template in _templates)
        Card(
          key: Key('report-template-${template.id}'),
          child: ListTile(
            leading: Icon(template.isBuiltin ? Icons.lock_outline : Icons.tune),
            title: Text(template.name),
            subtitle: Text(
              '${template.isBuiltin ? 'Built-in' : 'Custom'} · '
              '${template.includedSheets.length} sheets'
              '${template.isDefault ? ' · Default' : ''}',
            ),
            trailing: PopupMenuButton<String>(
              onSelected: (action) => _templateAction(template, action),
              itemBuilder: (context) => [
                if (!template.isBuiltin)
                  const PopupMenuItem(value: 'edit', child: Text('Edit')),
                const PopupMenuItem(
                  value: 'duplicate',
                  child: Text('Duplicate'),
                ),
                if (!template.isDefault)
                  const PopupMenuItem(
                    value: 'default',
                    child: Text('Set as default'),
                  ),
                if (!template.isBuiltin)
                  const PopupMenuItem(value: 'delete', child: Text('Delete')),
              ],
            ),
          ),
        ),
      const SizedBox(height: 20),
      Text(
        'DRIVER DUTY / OVERTIME',
        style: Theme.of(context).textTheme.titleLarge,
      ),
      const SizedBox(height: 8),
      if (widget.duties.isEmpty)
        const _EmptyCard(
          icon: Icons.schedule_outlined,
          text: 'No duty sessions for this day.',
        ),
      for (final duty in widget.duties) _DutyCard(duty: duty),
    ],
  );
}

String? _preferredTemplateId(List<ReportTemplate> templates) {
  for (final template in templates) {
    if (template.isDefault) return template.id;
  }
  return templates.isEmpty ? null : templates.first.id;
}

Future<String?> _showTemplateNameDialog(
  BuildContext context, {
  required String title,
  required String initialName,
}) async {
  var name = initialName;
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: TextFormField(
        key: const Key('report-template-name'),
        initialValue: initialName,
        autofocus: true,
        onChanged: (value) => name = value,
        decoration: const InputDecoration(labelText: 'Template name'),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('CANCEL'),
        ),
        FilledButton(
          onPressed: () {
            final trimmed = name.trim();
            if (trimmed.isNotEmpty) Navigator.pop(context, trimmed);
          },
          child: const Text('SAVE'),
        ),
      ],
    ),
  );
}

Future<ReportTemplateInput?> _showReportTemplateDialog(
  BuildContext context, {
  required ReportTemplate? existing,
  required ReportTemplate seed,
}) async {
  var name = existing?.name ?? '';
  final sheets = {...seed.includedSheets};
  final management = {...seed.managementDashboardColumns, 'asset'};
  final tipper = {...seed.tipperDailyColumns, 'asset'};
  final machinery = {...seed.machineryDailyColumns, 'asset'};
  String? validation;
  return showDialog<ReportTemplateInput>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, setDialogState) => AlertDialog(
        title: Text(existing == null ? 'New report template' : 'Edit template'),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextFormField(
                  key: const Key('report-template-editor-name'),
                  initialValue: name,
                  onChanged: (value) => name = value,
                  decoration: const InputDecoration(labelText: 'Template name'),
                ),
                const SizedBox(height: 16),
                Text('SHEETS', style: Theme.of(context).textTheme.titleMedium),
                for (final entry in reportSheetLabels.entries)
                  CheckboxListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    title: Text(entry.value),
                    value: sheets.contains(entry.key),
                    onChanged: (checked) => setDialogState(() {
                      checked == true
                          ? sheets.add(entry.key)
                          : sheets.remove(entry.key);
                    }),
                  ),
                _ReportColumnSelector(
                  title: 'MANAGEMENT DASHBOARD COLUMNS',
                  labels: managementReportColumnLabels,
                  selected: management,
                  onChanged: () => setDialogState(() {}),
                ),
                _ReportColumnSelector(
                  title: 'TIPPER DAILY COLUMNS',
                  labels: tipperReportColumnLabels,
                  selected: tipper,
                  onChanged: () => setDialogState(() {}),
                ),
                _ReportColumnSelector(
                  title: 'MACHINERY DAILY COLUMNS',
                  labels: machineryReportColumnLabels,
                  selected: machinery,
                  onChanged: () => setDialogState(() {}),
                ),
                if (validation != null)
                  Text(
                    validation!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('CANCEL'),
          ),
          FilledButton(
            key: const Key('save-report-template'),
            onPressed: () {
              final trimmedName = name.trim();
              if (trimmedName.isEmpty || sheets.isEmpty) {
                setDialogState(() {
                  validation = trimmedName.isEmpty
                      ? 'Enter a template name.'
                      : 'Select at least one sheet.';
                });
                return;
              }
              Navigator.pop(
                context,
                ReportTemplateInput(
                  name: trimmedName,
                  includedSheets: [
                    for (final id in reportSheetLabels.keys)
                      if (sheets.contains(id)) id,
                  ],
                  managementDashboardColumns: [
                    for (final id in managementReportColumnLabels.keys)
                      if (management.contains(id)) id,
                  ],
                  tipperDailyColumns: [
                    for (final id in tipperReportColumnLabels.keys)
                      if (tipper.contains(id)) id,
                  ],
                  machineryDailyColumns: [
                    for (final id in machineryReportColumnLabels.keys)
                      if (machinery.contains(id)) id,
                  ],
                ),
              );
            },
            child: const Text('SAVE'),
          ),
        ],
      ),
    ),
  );
}

class _ReportColumnSelector extends StatelessWidget {
  const _ReportColumnSelector({
    required this.title,
    required this.labels,
    required this.selected,
    required this.onChanged,
  });

  final String title;
  final Map<String, String> labels;
  final Set<String> selected;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(title, style: Theme.of(context).textTheme.titleSmall),
    children: [
      for (final entry in labels.entries)
        CheckboxListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          title: Text(entry.value),
          subtitle: entry.key == 'asset' ? const Text('Required') : null,
          value: selected.contains(entry.key),
          onChanged: entry.key == 'asset'
              ? null
              : (checked) {
                  checked == true
                      ? selected.add(entry.key)
                      : selected.remove(entry.key);
                  onChanged();
                },
        ),
    ],
  );
}

class _DutyCard extends StatelessWidget {
  const _DutyCard({required this.duty});
  final OwnerDutyReport duty;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  duty.driverName,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              _StatusChip(duty.status),
            ],
          ),
          Text('${duty.assetCode} · ${duty.siteName}'),
          const SizedBox(height: 8),
          _KeyValueRow('Duty start', _formatDate(duty.dutyStart)),
          if (duty.capabilities.supportsOdometer) ...[
            _KeyValueRow('START KM', _numberText(duty.startKm)),
            _KeyValueRow('END KM', _numberText(duty.endKm)),
            _KeyValueRow('DISTANCE', '${_numberText(duty.distanceKm)} KM'),
          ],
          if (duty.capabilities.supportsHourMeter) ...[
            _KeyValueRow('START HMR', _numberText(duty.startHmr)),
            _KeyValueRow('END HMR', _numberText(duty.endHmr)),
            _KeyValueRow(
              'MACHINE HOURS',
              '${_numberText(duty.machineHours)} h',
            ),
          ],
          if (duty.capabilities.supportsDiesel)
            _KeyValueRow(
              'DIESEL',
              duty.pendingDieselLitres > 0
                  ? '${_numberText(duty.verifiedDieselLitres)} L verified · ${_numberText(duty.pendingDieselLitres)} L pending'
                  : '${_numberText(duty.verifiedDieselLitres)} L',
            ),
          _KeyValueRow('Regular duty end', _formatDate(duty.regularEnds)),
          _KeyValueRow('Actual duty end', _formatDate(duty.actualEnd)),
          _KeyValueRow(
            'Overtime',
            duty.status == 'ACTIVE'
                ? 'OT accruing / current ${duty.overtimeMinutes} min'
                : '${duty.overtimeMinutes} min',
          ),
        ],
      ),
    ),
  );
}

class _EvidenceDialog extends StatelessWidget {
  const _EvidenceDialog({required this.title, required this.loader});
  final String title;
  final Future<Uint8List> Function() loader;

  @override
  Widget build(BuildContext context) => Dialog(
    insetPadding: const EdgeInsets.all(12),
    child: FutureBuilder<Uint8List>(
      future: loader(),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const SizedBox(
            height: 360,
            child: Center(child: CircularProgressIndicator()),
          );
        }
        if (snapshot.hasError || snapshot.data == null) {
          return SizedBox(
            height: 240,
            child: Center(child: Text('Evidence could not be loaded.')),
          );
        }
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AppBar(
              title: Text(title),
              automaticallyImplyLeading: false,
              actions: [
                IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close),
                ),
              ],
            ),
            Flexible(
              child: InteractiveViewer(
                child: Image.memory(snapshot.data!, fit: BoxFit.contain),
              ),
            ),
          ],
        );
      },
    ),
  );
}

class _RoleScaffold extends StatelessWidget {
  const _RoleScaffold({
    required this.title,
    required this.subtitle,
    required this.body,
    required this.onRefresh,
    required this.onSignOut,
    this.offline = false,
    this.bottomNavigationBar,
  });
  final String title;
  final String subtitle;
  final Widget body;
  final Future<void> Function() onRefresh;
  final SignOut onSignOut;
  final bool offline;
  final Widget? bottomNavigationBar;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 18)),
          Text(subtitle, style: Theme.of(context).textTheme.labelSmall),
        ],
      ),
      actions: [
        if (isPilotBuild)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 4),
            child: Center(child: Text('PILOT')),
          ),
        IconButton(
          onPressed: onRefresh,
          tooltip: 'Refresh',
          icon: const Icon(Icons.refresh),
        ),
        IconButton(
          onPressed: onSignOut,
          tooltip: 'Sign out',
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: Column(
      children: [
        if (offline) const _OfflineBanner(),
        Expanded(child: body),
      ],
    ),
    bottomNavigationBar: bottomNavigationBar,
  );
}

class _MetricGrid extends StatelessWidget {
  const _MetricGrid({required this.metrics});
  final List<_Metric> metrics;
  @override
  Widget build(BuildContext context) => GridView.count(
    crossAxisCount: 2,
    crossAxisSpacing: 10,
    mainAxisSpacing: 10,
    childAspectRatio: 1.55,
    shrinkWrap: true,
    physics: const NeverScrollableScrollPhysics(),
    children: [
      for (final metric in metrics)
        Card(
          color: metric.danger
              ? Theme.of(context).colorScheme.errorContainer
              : null,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(metric.icon),
                const SizedBox(height: 8),
                Text(
                  metric.value,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Text(
                  metric.label,
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          ),
        ),
    ],
  );
}

class _Metric {
  const _Metric(this.label, this.value, this.icon, {this.danger = false});
  final String label;
  final String value;
  final IconData icon;
  final bool danger;
}

class _EmergencyCard extends StatelessWidget {
  const _EmergencyCard({
    required this.event,
    required this.showSite,
    required this.onCall,
    required this.onAcknowledge,
    required this.onResolve,
  });
  final SupervisorEvent event;
  final bool showSite;
  final VoidCallback onCall;
  final VoidCallback onAcknowledge;
  final VoidCallback onResolve;
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'EMERGENCY',
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text('${event.driverName} · ${event.tipperRegistration}'),
          Text(
            showSite
                ? '${event.siteName} · ${_formatDate(event.deviceCreatedAt)}'
                : _formatDate(event.deviceCreatedAt),
          ),
          if (event.emergencyDescription != null)
            Text(event.emergencyDescription!),
          Wrap(
            spacing: 8,
            children: [
              if (event.driverPhone != null)
                TextButton.icon(
                  onPressed: onCall,
                  icon: const Icon(Icons.call_outlined),
                  label: const Text('CALL DRIVER'),
                ),
              if (event.emergencyStatus == 'OPEN')
                FilledButton(
                  onPressed: onAcknowledge,
                  child: const Text('ACKNOWLEDGE'),
                ),
              if (event.emergencyStatus == 'ACKNOWLEDGED')
                FilledButton(
                  onPressed: onResolve,
                  child: const Text('RESOLVE'),
                ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _StatusChip extends StatelessWidget {
  const _StatusChip(this.status);
  final String status;
  @override
  Widget build(BuildContext context) => Chip(
    label: Text(status.replaceAll('_', ' ')),
    visualDensity: VisualDensity.compact,
  );
}

class _KeyValueRow extends StatelessWidget {
  const _KeyValueRow(this.label, this.value);
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 2),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
      ],
    ),
  );
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function() onRetry;
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: ListTile(
      leading: const Icon(Icons.error_outline),
      title: Text(message),
      trailing: IconButton(onPressed: onRetry, icon: const Icon(Icons.refresh)),
    ),
  );
}

class _MessageBanner extends StatelessWidget {
  const _MessageBanner({required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      leading: const Icon(Icons.check_circle_outline),
      title: Text(message),
    ),
  );
}

class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner();
  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    color: Theme.of(context).colorScheme.tertiaryContainer,
    padding: const EdgeInsets.all(8),
    child: const Text(
      'OFFLINE · Showing the last available state',
      textAlign: TextAlign.center,
    ),
  );
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.icon, required this.text});
  final IconData icon;
  final String text;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          Icon(icon),
          const SizedBox(width: 12),
          Expanded(child: Text(text)),
        ],
      ),
    ),
  );
}

String _friendlyError(ApiException error) {
  if (error.statusCode == 401) {
    return 'Your session expired. Please sign in again.';
  }
  if (error.isRetryable) {
    return 'Fleet Manager server is unavailable. Check the Pilot server URL and connection.';
  }
  if (error.statusCode == 403) {
    return 'This account is not authorized for this role or data.';
  }
  return error.message.isEmpty
      ? 'Request could not be completed.'
      : error.message;
}

String _formatDate(DateTime? value) {
  if (value == null) return 'Time unavailable';
  return '${value.toLocal().day.toString().padLeft(2, '0')}/${value.toLocal().month.toString().padLeft(2, '0')} ${value.toLocal().hour.toString().padLeft(2, '0')}:${value.toLocal().minute.toString().padLeft(2, '0')}';
}

String _numberText(double? value) => value == null
    ? '—'
    : value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 2);
