import 'package:flutter/material.dart';

import 'data/api_client.dart';
import 'domain/role_models.dart';

typedef OwnerUnauthorized = Future<void> Function();

enum OwnerFleetFilter { all, owned, rented, inactive }

class OwnerFleetScreen extends StatefulWidget {
  const OwnerFleetScreen({required this.api, this.onUnauthorized, super.key});

  final OwnerAssetApi api;
  final OwnerUnauthorized? onUnauthorized;

  @override
  State<OwnerFleetScreen> createState() => _OwnerFleetScreenState();
}

class _OwnerFleetScreenState extends State<OwnerFleetScreen> {
  final _search = TextEditingController();
  List<OwnerAsset> _assets = const [];
  OwnerFleetFilter _filter = OwnerFleetFilter.all;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _search.addListener(_searchChanged);
    _load();
  }

  @override
  void dispose() {
    _search
      ..removeListener(_searchChanged)
      ..dispose();
    super.dispose();
  }

  void _searchChanged() => setState(() {});

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final assets = await widget.api.ownerAssets();
      if (!mounted) return;
      setState(() => _assets = assets);
    } on ApiException catch (error) {
      if (error.isUnauthorized && widget.onUnauthorized != null) {
        await widget.onUnauthorized!();
        return;
      }
      if (mounted) setState(() => _error = error.message);
    } on Object {
      if (mounted) setState(() => _error = 'Fleet could not be loaded.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<OwnerAsset> get _visibleAssets {
    final query = _search.text.trim().toLowerCase();
    return _assets.where((asset) {
      final filterMatches = switch (_filter) {
        OwnerFleetFilter.all => true,
        OwnerFleetFilter.owned => asset.isOwned,
        OwnerFleetFilter.rented => asset.isRented,
        OwnerFleetFilter.inactive => !asset.isActive,
      };
      if (!filterMatches) return false;
      if (query.isEmpty) return true;
      return [
        asset.assetCode,
        asset.registrationNumber,
        asset.shortName,
        asset.rentalPartyName,
      ].whereType<String>().any((value) => value.toLowerCase().contains(query));
    }).toList();
  }

  Future<void> _add() async {
    final saved = await Navigator.of(context).push<OwnerAsset>(
      MaterialPageRoute(builder: (_) => OwnerAssetFormScreen(api: widget.api)),
    );
    if (saved != null) await _load();
  }

  Future<void> _edit(OwnerAsset asset) async {
    final saved = await Navigator.of(context).push<OwnerAsset>(
      MaterialPageRoute(
        builder: (_) => OwnerAssetFormScreen(api: widget.api, asset: asset),
      ),
    );
    if (saved != null) await _load();
  }

  Future<void> _assign(OwnerAsset asset) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            OwnerAssetDeploymentScreen(api: widget.api, asset: asset),
      ),
    );
    if (changed == true) await _load();
  }

  Future<void> _view(OwnerAsset asset) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => OwnerAssetDetailScreen(api: widget.api, asset: asset),
      ),
    );
    await _load();
  }

  Future<void> _changeDriver(OwnerAsset asset) async {
    final api = widget.api;
    if (api is! DriverAssignmentApi) return;
    final changed = await showDriverAssignmentDialog(
      context,
      api: api as DriverAssignmentApi,
      assetId: asset.id,
      assetLabel: asset.registrationNumber ?? asset.assetCode,
      siteLabel: asset.currentDeployment!.siteName,
      hasAssignment: asset.activeAssignment != null,
    );
    if (changed == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final visible = _visibleAssets;
    final owned = _assets.where((asset) => asset.isOwned).length;
    final rented = _assets.where((asset) => asset.isRented).length;
    final inactive = _assets.where((asset) => !asset.isActive).length;
    return RefreshIndicator(
      onRefresh: _load,
      child: CustomScrollView(
        key: const Key('owner-fleet-scroll'),
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            sliver: SliverToBoxAdapter(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'FLEET',
                          style: Theme.of(context).textTheme.headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w800),
                        ),
                      ),
                      FilledButton.icon(
                        key: const Key('add-tipper'),
                        onPressed: _add,
                        icon: const Icon(Icons.add),
                        label: const Text('ADD TIPPER'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _FleetMetric(
                        label: 'Total Assets',
                        value: _assets.length,
                      ),
                      _FleetMetric(label: 'Owned', value: owned),
                      _FleetMetric(label: 'Rented', value: rented),
                      _FleetMetric(label: 'Inactive', value: inactive),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 8,
                    children: [
                      for (final entry in const [
                        (OwnerFleetFilter.all, 'All'),
                        (OwnerFleetFilter.owned, 'Owned'),
                        (OwnerFleetFilter.rented, 'Rented'),
                        (OwnerFleetFilter.inactive, 'Inactive'),
                      ])
                        FilterChip(
                          key: Key('fleet-filter-${entry.$2.toLowerCase()}'),
                          label: Text(entry.$2),
                          selected: _filter == entry.$1,
                          onSelected: (_) => setState(() => _filter = entry.$1),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    key: const Key('fleet-search'),
                    controller: _search,
                    decoration: const InputDecoration(
                      labelText: 'Search fleet',
                      hintText: 'Asset code, registration, name, rental party',
                      prefixIcon: Icon(Icons.search),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Material(
                      key: const Key('fleet-api-error'),
                      color: Theme.of(context).colorScheme.errorContainer,
                      borderRadius: BorderRadius.circular(12),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          children: [
                            Expanded(child: Text(_error!)),
                            TextButton(
                              onPressed: _load,
                              child: const Text('RETRY'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  if (_loading) ...[
                    const SizedBox(height: 12),
                    const LinearProgressIndicator(),
                  ],
                ],
              ),
            ),
          ),
          if (!_loading && visible.isEmpty)
            const SliverFillRemaining(
              hasScrollBody: false,
              child: Center(child: Text('No fleet assets match this view.')),
            )
          else
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
              sliver: SliverList.builder(
                itemCount: visible.length,
                itemBuilder: (context, index) {
                  final asset = visible[index];
                  return OwnerAssetCard(
                    key: Key('owner-asset-${asset.id}'),
                    asset: asset,
                    onView: () => _view(asset),
                    onEdit: () => _edit(asset),
                    onAssign: () => _assign(asset),
                    onDriver: widget.api is DriverAssignmentApi
                        ? () => _changeDriver(asset)
                        : null,
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _FleetMetric extends StatelessWidget {
  const _FleetMetric({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) => Container(
    width: 112,
    padding: const EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$value', style: Theme.of(context).textTheme.headlineSmall),
        Text(label, style: Theme.of(context).textTheme.labelMedium),
      ],
    ),
  );
}

class OwnerAssetCard extends StatelessWidget {
  const OwnerAssetCard({
    required this.asset,
    required this.onView,
    required this.onEdit,
    required this.onAssign,
    this.onDriver,
    super.key,
  });

  final OwnerAsset asset;
  final VoidCallback onView;
  final VoidCallback onEdit;
  final VoidCallback onAssign;
  final VoidCallback? onDriver;

  @override
  Widget build(BuildContext context) {
    final assignment = asset.activeAssignment;
    final deployment = asset.currentDeployment;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              asset.registrationNumber ?? asset.assetCode,
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 2),
            Text(asset.shortName ?? asset.assetCode),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                _FleetChip(label: asset.assetType, tone: _ChipTone.neutral),
                _FleetChip(
                  label: asset.ownershipType,
                  tone: asset.isRented
                      ? _ChipTone.attention
                      : _ChipTone.neutral,
                ),
                _FleetChip(
                  label: asset.status,
                  tone: asset.isActive ? _ChipTone.success : _ChipTone.inactive,
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (asset.isRented && asset.rentalPartyName != null)
              Text(
                asset.rentalPartyName!,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            Text('Site: ${deployment?.siteName ?? 'Not assigned'}'),
            Text('Driver: ${assignment?.driverName ?? 'Unassigned'}'),
            const SizedBox(height: 10),
            Wrap(
              alignment: WrapAlignment.end,
              spacing: 8,
              runSpacing: 8,
              children: [
                if (asset.isActive && deployment == null) ...[
                  OutlinedButton(
                    key: Key('assign-site-${asset.id}'),
                    onPressed: onAssign,
                    child: const Text('ASSIGN TO SITE'),
                  ),
                ],
                if (asset.isActive &&
                    asset.assetType == 'TIPPER' &&
                    deployment != null &&
                    onDriver != null)
                  OutlinedButton(
                    key: Key('assign-driver-${asset.id}'),
                    onPressed: onDriver,
                    child: Text(
                      assignment == null ? 'ASSIGN DRIVER' : 'CHANGE DRIVER',
                    ),
                  ),
                OutlinedButton(onPressed: onView, child: const Text('VIEW')),
                FilledButton.tonal(
                  onPressed: onEdit,
                  child: const Text('EDIT'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

enum _ChipTone { success, attention, inactive, neutral }

class _FleetChip extends StatelessWidget {
  const _FleetChip({required this.label, required this.tone});

  final String label;
  final _ChipTone tone;

  @override
  Widget build(BuildContext context) {
    final colors = switch (tone) {
      _ChipTone.success => (const Color(0xFFE2F4E8), const Color(0xFF176B3A)),
      _ChipTone.attention => (const Color(0xFFFFF1D6), const Color(0xFF8A5700)),
      _ChipTone.inactive => (const Color(0xFFE8EAED), const Color(0xFF5F6368)),
      _ChipTone.neutral => (const Color(0xFFE5F0F1), const Color(0xFF155E63)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: colors.$1,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: colors.$2,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class OwnerAssetFormScreen extends StatefulWidget {
  const OwnerAssetFormScreen({required this.api, this.asset, super.key});

  final OwnerAssetApi api;
  final OwnerAsset? asset;

  @override
  State<OwnerAssetFormScreen> createState() => _OwnerAssetFormScreenState();
}

class _OwnerAssetFormScreenState extends State<OwnerAssetFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _assetCode;
  late final TextEditingController _registration;
  late final TextEditingController _shortName;
  late final TextEditingController _rentalParty;
  late final TextEditingController _manufacturer;
  late final TextEditingController _model;
  late String _ownership;
  DateTime? _rentalStart;
  DateTime? _rentalEnd;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.asset != null;
  bool get _rented => _ownership == 'RENTED';

  @override
  void initState() {
    super.initState();
    final asset = widget.asset;
    _assetCode = TextEditingController(text: asset?.assetCode);
    _registration = TextEditingController(text: asset?.registrationNumber);
    _shortName = TextEditingController(text: asset?.shortName);
    _rentalParty = TextEditingController(text: asset?.rentalPartyName);
    _manufacturer = TextEditingController(text: asset?.manufacturer);
    _model = TextEditingController(text: asset?.model);
    _ownership = asset?.ownershipType ?? 'OWNED';
    _rentalStart = asset?.rentalStartDate;
    _rentalEnd = asset?.rentalEndDate;
  }

  @override
  void dispose() {
    _assetCode.dispose();
    _registration.dispose();
    _shortName.dispose();
    _rentalParty.dispose();
    _manufacturer.dispose();
    _model.dispose();
    super.dispose();
  }

  String? _required(String? value, String label) =>
      value == null || value.trim().isEmpty ? '$label is required.' : null;

  Future<void> _pickDate({required bool start}) async {
    final current = start ? _rentalStart : _rentalEnd;
    final picked = await showDatePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
      initialDate: current ?? DateTime.now(),
    );
    if (picked != null) {
      setState(() {
        if (start) {
          _rentalStart = picked;
        } else {
          _rentalEnd = picked;
        }
      });
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    if (_rented &&
        _rentalStart != null &&
        _rentalEnd != null &&
        _rentalEnd!.isBefore(_rentalStart!)) {
      setState(
        () => _error = 'Rental end date cannot be before rental start date.',
      );
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final input = OwnerAssetInput(
      assetCode: _assetCode.text.trim(),
      registrationNumber: _registration.text.trim(),
      shortName: _nullable(_shortName.text),
      ownershipType: _ownership,
      manufacturer: _nullable(_manufacturer.text),
      model: _nullable(_model.text),
      rentalPartyName: _rented ? _nullable(_rentalParty.text) : null,
      rentalStartDate: _rented ? _rentalStart : null,
      rentalEndDate: _rented ? _rentalEnd : null,
    );
    try {
      final saved = _editing
          ? await widget.api.updateOwnerAsset(widget.asset!.id, input)
          : await widget.api.createOwnerAsset(input);
      if (mounted) {
        Navigator.pop(context, saved);
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on Object {
      if (mounted) setState(() => _error = 'Tipper could not be saved.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(_editing ? 'EDIT TIPPER' : 'ADD TIPPER')),
    body: Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextFormField(
            key: const Key('asset-code-field'),
            controller: _assetCode,
            decoration: const InputDecoration(labelText: 'Asset Code'),
            validator: (value) => _required(value, 'Asset code'),
          ),
          const SizedBox(height: 12),
          TextFormField(
            key: const Key('registration-field'),
            controller: _registration,
            decoration: const InputDecoration(labelText: 'Registration Number'),
            validator: (value) => _required(value, 'Registration number'),
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _shortName,
            decoration: const InputDecoration(labelText: 'Short Name'),
          ),
          const SizedBox(height: 18),
          Text('Ownership', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            key: const Key('ownership-selector'),
            segments: const [
              ButtonSegment(value: 'OWNED', label: Text('OWNED')),
              ButtonSegment(value: 'RENTED', label: Text('RENTED')),
            ],
            selected: {_ownership},
            onSelectionChanged: (values) =>
                setState(() => _ownership = values.single),
          ),
          if (_rented) ...[
            const SizedBox(height: 16),
            Container(
              key: const Key('rental-fields'),
              child: Column(
                children: [
                  TextFormField(
                    key: const Key('rental-party-field'),
                    controller: _rentalParty,
                    decoration: const InputDecoration(
                      labelText: 'Rental Party',
                    ),
                    validator: (value) =>
                        _rented ? _required(value, 'Rental party') : null,
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _DateField(
                          label: 'Rental Start',
                          value: _rentalStart,
                          onTap: () => _pickDate(start: true),
                          onClear: () => setState(() => _rentalStart = null),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _DateField(
                          label: 'Rental End',
                          value: _rentalEnd,
                          onTap: () => _pickDate(start: false),
                          onClear: () => setState(() => _rentalEnd = null),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 12),
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('Manufacturer and model (optional)'),
            children: [
              TextFormField(
                controller: _manufacturer,
                decoration: const InputDecoration(labelText: 'Manufacturer'),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _model,
                decoration: const InputDecoration(labelText: 'Model'),
              ),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(
              _error!,
              key: const Key('asset-form-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _saving ? null : () => Navigator.pop(context),
                  child: const Text('CANCEL'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton(
                  key: const Key('save-tipper'),
                  onPressed: _saving ? null : _save,
                  child: Text(_saving ? 'SAVING…' : 'SAVE TIPPER'),
                ),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}

class _DateField extends StatelessWidget {
  const _DateField({
    required this.label,
    required this.value,
    required this.onTap,
    required this.onClear,
  });

  final String label;
  final DateTime? value;
  final VoidCallback onTap;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) => InputDecorator(
    decoration: InputDecoration(labelText: label),
    child: Row(
      children: [
        Expanded(child: Text(_dateText(value))),
        if (value != null)
          IconButton(
            tooltip: 'Clear $label',
            onPressed: onClear,
            icon: const Icon(Icons.clear, size: 18),
          ),
        IconButton(
          tooltip: 'Choose $label',
          onPressed: onTap,
          icon: const Icon(Icons.calendar_today_outlined, size: 18),
        ),
      ],
    ),
  );
}

class OwnerAssetDetailScreen extends StatefulWidget {
  const OwnerAssetDetailScreen({
    required this.api,
    required this.asset,
    super.key,
  });

  final OwnerAssetApi api;
  final OwnerAsset asset;

  @override
  State<OwnerAssetDetailScreen> createState() => _OwnerAssetDetailScreenState();
}

class _OwnerAssetDetailScreenState extends State<OwnerAssetDetailScreen> {
  late OwnerAsset _asset;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _asset = widget.asset;
  }

  Future<void> _edit() async {
    final updated = await Navigator.of(context).push<OwnerAsset>(
      MaterialPageRoute(
        builder: (_) => OwnerAssetFormScreen(api: widget.api, asset: _asset),
      ),
    );
    if (updated != null && mounted) setState(() => _asset = updated);
  }

  Future<void> _toggleStatus() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final updated = _asset.isActive
          ? await widget.api.deactivateOwnerAsset(_asset.id)
          : await widget.api.reactivateOwnerAsset(_asset.id);
      if (mounted) {
        setState(() => _asset = updated);
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() => _error = error.message);
      }
    } on Object {
      if (mounted) {
        setState(() => _error = 'Asset status could not be changed.');
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _changeDeployment() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            OwnerAssetDeploymentScreen(api: widget.api, asset: _asset),
      ),
    );
    if (changed == true) await _reload();
  }

  Future<void> _removeDeployment() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.removeOwnerAssetDeployment(_asset.id);
      await _reload();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _changeDriver() async {
    final api = widget.api;
    if (api is! DriverAssignmentApi) return;
    final changed = await showDriverAssignmentDialog(
      context,
      api: api as DriverAssignmentApi,
      assetId: _asset.id,
      assetLabel: _asset.registrationNumber ?? _asset.assetCode,
      siteLabel: _asset.currentDeployment!.siteName,
      hasAssignment: _asset.activeAssignment != null,
    );
    if (changed == true) await _reload();
  }

  Future<void> _reload() async {
    final updated = await widget.api.ownerAsset(_asset.id);
    if (mounted) setState(() => _asset = updated);
  }

  @override
  Widget build(BuildContext context) {
    final assignment = _asset.activeAssignment;
    final deployment = _asset.currentDeployment;
    return Scaffold(
      appBar: AppBar(title: const Text('ASSET DETAIL')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            _asset.registrationNumber ?? _asset.assetCode,
            style: Theme.of(
              context,
            ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
          ),
          Text(_asset.shortName ?? _asset.assetCode),
          const SizedBox(height: 16),
          _DetailSection(
            title: 'Asset identity',
            rows: {
              'Asset code': _asset.assetCode,
              'Type': _asset.assetType,
              'Registration': _asset.registrationNumber ?? '—',
              'Manufacturer': _asset.manufacturer ?? '—',
              'Model': _asset.model ?? '—',
            },
          ),
          if (_asset.isActive &&
              _asset.assetType == 'TIPPER' &&
              deployment != null &&
              widget.api is DriverAssignmentApi)
            FilledButton.tonal(
              key: const Key('asset-driver-action'),
              onPressed: _busy ? null : _changeDriver,
              child: Text(
                assignment == null ? 'ASSIGN DRIVER' : 'CHANGE DRIVER',
              ),
            ),
          _DetailSection(
            title: 'Ownership and status',
            rows: {
              'Ownership': _asset.ownershipType,
              'Status': _asset.status,
              if (_asset.isRented)
                'Rental party': _asset.rentalPartyName ?? '—',
              if (_asset.isRented)
                'Rental start': _dateText(_asset.rentalStartDate),
              if (_asset.isRented)
                'Rental end': _dateText(_asset.rentalEndDate),
            },
          ),
          _DetailSection(
            title: 'DEPLOYMENT',
            rows: deployment == null
                ? const {'Current Site': 'Not assigned'}
                : {
                    'Current Site': deployment.siteName,
                    'Since': _dateText(deployment.startsAt),
                  },
          ),
          Row(
            children: [
              Expanded(
                child: FilledButton.tonal(
                  key: const Key('asset-deployment-action'),
                  onPressed: _busy || !_asset.isActive
                      ? null
                      : _changeDeployment,
                  child: Text(
                    deployment == null ? 'ASSIGN TO SITE' : 'MOVE SITE',
                  ),
                ),
              ),
              if (deployment != null) ...[
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton(
                    key: const Key('remove-site-deployment'),
                    onPressed: _busy ? null : _removeDeployment,
                    child: const Text('REMOVE FROM SITE'),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 12),
          _DetailSection(
            key: const Key('current-driver-assignment'),
            title: 'Current Driver assignment',
            rows: assignment == null
                ? const {'Status': 'No active assignment'}
                : {
                    'Site': assignment.siteName,
                    'Driver': assignment.driverName,
                    'Assigned since': _dateText(assignment.startsAt),
                  },
          ),
          if (_error != null)
            Text(
              _error!,
              key: const Key('asset-detail-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          const SizedBox(height: 16),
          FilledButton.tonal(
            onPressed: _busy ? null : _edit,
            child: const Text('EDIT'),
          ),
          const SizedBox(height: 10),
          FilledButton(
            key: const Key('asset-status-action'),
            onPressed: _busy ? null : _toggleStatus,
            style: _asset.isActive
                ? FilledButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.error,
                  )
                : null,
            child: Text(_asset.isActive ? 'DEACTIVATE' : 'REACTIVATE'),
          ),
        ],
      ),
    );
  }
}

class OwnerAssetDeploymentScreen extends StatefulWidget {
  const OwnerAssetDeploymentScreen({
    required this.api,
    required this.asset,
    this.fixedSite,
    super.key,
  });

  final OwnerAssetApi api;
  final OwnerAsset asset;
  final OwnerManagedSite? fixedSite;

  @override
  State<OwnerAssetDeploymentScreen> createState() =>
      _OwnerAssetDeploymentScreenState();
}

class _OwnerAssetDeploymentScreenState
    extends State<OwnerAssetDeploymentScreen> {
  List<OwnerManagedSite> _sites = const [];
  String? _selectedSite;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _selectedSite = widget.fixedSite?.id;
    _load();
  }

  Future<void> _load() async {
    try {
      final sites = await widget.api.ownerDeploymentSites();
      if (mounted) {
        setState(() {
          _sites = sites
              .where(
                (site) =>
                    site.isActive &&
                    site.id != widget.asset.currentDeployment?.siteId,
              )
              .toList();
          _loading = false;
        });
      }
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _loading = false;
          _error = error.message;
        });
      }
    }
  }

  Future<void> _save() async {
    final siteId = _selectedSite;
    if (siteId == null) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.api.deployOwnerAsset(widget.asset.id, siteId);
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        widget.asset.currentDeployment == null ? 'ASSIGN TO SITE' : 'MOVE SITE',
      ),
    ),
    body: ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Asset', style: Theme.of(context).textTheme.labelLarge),
        Text(
          '${widget.asset.assetCode} / '
          '${widget.asset.registrationNumber ?? widget.asset.shortName ?? widget.asset.assetCode}',
          key: const Key('deployment-asset'),
        ),
        const SizedBox(height: 18),
        if (_loading)
          const LinearProgressIndicator()
        else if (widget.fixedSite != null)
          InputDecorator(
            decoration: const InputDecoration(labelText: 'Site'),
            child: Text(widget.fixedSite!.name),
          )
        else
          DropdownButtonFormField<String>(
            key: const Key('deployment-site'),
            initialValue: _selectedSite,
            decoration: const InputDecoration(labelText: 'Site'),
            items: _sites
                .map(
                  (site) =>
                      DropdownMenuItem(value: site.id, child: Text(site.name)),
                )
                .toList(),
            onChanged: (value) => setState(() => _selectedSite = value),
          ),
        if (!_loading && _sites.isEmpty && widget.fixedSite == null)
          const Padding(
            padding: EdgeInsets.only(top: 12),
            child: Text('No active destination Sites are available.'),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              _error!,
              key: const Key('deployment-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        const SizedBox(height: 24),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: _saving ? null : () => Navigator.pop(context),
                child: const Text('CANCEL'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                key: const Key('confirm-deployment'),
                onPressed: _saving || _selectedSite == null ? null : _save,
                child: Text(_saving ? 'SAVING…' : 'ASSIGN'),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}

class _DetailSection extends StatelessWidget {
  const _DetailSection({required this.title, required this.rows, super.key});

  final String title;
  final Map<String, String> rows;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          for (final entry in rows.entries)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(width: 112, child: Text(entry.key)),
                  Expanded(
                    child: Text(
                      entry.value,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}

String? _nullable(String value) {
  final clean = value.trim();
  return clean.isEmpty ? null : clean;
}

String _dateText(DateTime? value) =>
    value == null ? 'Not set' : value.toIso8601String().substring(0, 10);

Future<bool?> showDriverAssignmentDialog(
  BuildContext context, {
  required DriverAssignmentApi api,
  required String assetId,
  required String assetLabel,
  required String siteLabel,
  required bool hasAssignment,
  String? supervisorSiteId,
}) async {
  var drivers = <DriverCandidate>[];
  String? selected;
  String? error;
  var loading = true;
  var saving = false;
  var requested = false;
  return showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) => StatefulBuilder(
      builder: (context, setDialogState) {
        if (!requested) {
          requested = true;
          Future<void>.microtask(() async {
            try {
              final value = await api.eligibleDrivers(
                assetId,
                supervisorSiteId: supervisorSiteId,
              );
              if (!dialogContext.mounted) return;
              setDialogState(() {
                drivers = value;
                selected = value.isEmpty ? null : value.first.membershipId;
                loading = false;
              });
            } on Object catch (caught) {
              if (!dialogContext.mounted) return;
              setDialogState(() {
                error = caught is ApiException
                    ? caught.message
                    : 'Drivers could not be loaded.';
                loading = false;
              });
            }
          });
        }
        Future<void> save() async {
          final driverId = selected;
          if (driverId == null) return;
          setDialogState(() => saving = true);
          try {
            await api.assignDriver(
              assetId,
              driverId,
              supervisorSiteId: supervisorSiteId,
              reassign: hasAssignment,
            );
            if (dialogContext.mounted) Navigator.pop(dialogContext, true);
          } on ApiException catch (caught) {
            setDialogState(() {
              error = caught.message;
              saving = false;
            });
          }
        }

        Future<void> unassign() async {
          setDialogState(() => saving = true);
          try {
            await api.unassignDriver(
              assetId,
              supervisorSiteId: supervisorSiteId,
            );
            if (dialogContext.mounted) Navigator.pop(dialogContext, true);
          } on ApiException catch (caught) {
            setDialogState(() {
              error = caught.message;
              saving = false;
            });
          }
        }

        return AlertDialog(
          title: Text(
            hasAssignment
                ? 'CHANGE DRIVER / OPERATOR · $assetLabel'
                : 'ASSIGN DRIVER / OPERATOR · $assetLabel',
          ),
          content: SizedBox(
            width: 420,
            child: loading
                ? const LinearProgressIndicator()
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      InputDecorator(
                        key: const Key('assignment-site'),
                        decoration: const InputDecoration(labelText: 'Site'),
                        child: Text(siteLabel),
                      ),
                      const SizedBox(height: 12),
                      if (drivers.isEmpty)
                        const Text(
                          'No eligible Driver / Operator is available.',
                        )
                      else
                        DropdownButtonFormField<String>(
                          key: const Key('eligible-driver'),
                          initialValue: selected,
                          decoration: const InputDecoration(
                            labelText: 'Driver / Operator',
                          ),
                          items: drivers
                              .map(
                                (driver) => DropdownMenuItem(
                                  value: driver.membershipId,
                                  child: Text(driver.displayName),
                                ),
                              )
                              .toList(),
                          onChanged: saving
                              ? null
                              : (value) =>
                                    setDialogState(() => selected = value),
                        ),
                      if (error != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          error!,
                          key: const Key('driver-assignment-error'),
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ],
                    ],
                  ),
          ),
          actions: [
            if (hasAssignment)
              TextButton(
                key: const Key('unassign-driver'),
                onPressed: saving ? null : unassign,
                child: const Text('UNASSIGN'),
              ),
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(dialogContext),
              child: const Text('CANCEL'),
            ),
            FilledButton(
              key: const Key('confirm-driver-assignment'),
              onPressed: saving || loading || selected == null ? null : save,
              child: Text(saving ? 'SAVING…' : 'SAVE'),
            ),
          ],
        );
      },
    ),
  );
}
