import 'package:flutter/material.dart';

import 'data/api_client.dart';
import 'domain/role_models.dart';
import 'owner_fleet.dart' show OwnerUnauthorized;

enum OwnerPeopleFilter { all, drivers, supervisors, invited, inactive }

class OwnerPeopleScreen extends StatefulWidget {
  const OwnerPeopleScreen({required this.api, this.onUnauthorized, super.key});

  final OwnerPeopleSiteApi api;
  final OwnerUnauthorized? onUnauthorized;

  @override
  State<OwnerPeopleScreen> createState() => _OwnerPeopleScreenState();
}

class _OwnerPeopleScreenState extends State<OwnerPeopleScreen> {
  final _search = TextEditingController();
  List<OwnerPerson> _people = const [];
  OwnerPeopleFilter _filter = OwnerPeopleFilter.all;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _search.addListener(_changed);
    _load();
  }

  @override
  void dispose() {
    _search
      ..removeListener(_changed)
      ..dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final people = await widget.api.ownerPeople();
      if (mounted) setState(() => _people = people);
    } on ApiException catch (error) {
      if (error.isUnauthorized && widget.onUnauthorized != null) {
        await widget.onUnauthorized!();
      } else if (mounted) {
        setState(() => _error = error.message);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<OwnerPerson> get _visible {
    final query = _search.text.trim().toLowerCase();
    return _people.where((person) {
      final filtered = switch (_filter) {
        OwnerPeopleFilter.all => true,
        OwnerPeopleFilter.drivers => person.role == 'DRIVER',
        OwnerPeopleFilter.supervisors => person.isSupervisor,
        OwnerPeopleFilter.invited => person.isInvited,
        OwnerPeopleFilter.inactive => person.status == 'INACTIVE',
      };
      return filtered &&
          (query.isEmpty ||
              person.displayName.toLowerCase().contains(query) ||
              person.phone.contains(query));
    }).toList();
  }

  Future<void> _form([OwnerPerson? person]) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _PersonForm(api: widget.api, person: person),
    );
    if (saved == true) await _load();
  }

  Future<void> _toggle(OwnerPerson person) async {
    try {
      await widget.api.setOwnerPersonActive(
        person.membershipId,
        !person.isActive,
      );
      await _load();
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final active = _people.where((person) => person.isActive).length;
    final invited = _people.where((person) => person.isInvited).length;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        key: const Key('owner-people-list'),
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'PEOPLE',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              FilledButton.icon(
                key: const Key('invite-person'),
                onPressed: () => _form(),
                icon: const Icon(Icons.person_add_alt_1),
                label: const Text('INVITE'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _CountChip(label: 'Total', count: _people.length),
              _CountChip(label: 'Active', count: active),
              _CountChip(label: 'Invited', count: invited),
              _CountChip(
                label: 'Inactive',
                count: _people.length - active - invited,
              ),
            ],
          ),
          const SizedBox(height: 12),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final entry in const [
                  (OwnerPeopleFilter.all, 'All'),
                  (OwnerPeopleFilter.drivers, 'Drivers'),
                  (OwnerPeopleFilter.supervisors, 'Supervisors'),
                  (OwnerPeopleFilter.invited, 'Invited'),
                  (OwnerPeopleFilter.inactive, 'Inactive'),
                ])
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      label: Text(entry.$2),
                      selected: _filter == entry.$1,
                      onSelected: (_) => setState(() => _filter = entry.$1),
                    ),
                  ),
              ],
            ),
          ),
          TextField(
            key: const Key('people-search'),
            controller: _search,
            decoration: const InputDecoration(
              labelText: 'Search people',
              prefixIcon: Icon(Icons.search),
            ),
          ),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) _ErrorCard(message: _error!, onRetry: _load),
          if (!_loading && _visible.isEmpty)
            const _EmptyCard(
              icon: Icons.people_outline,
              text: 'No people match this view.',
            ),
          for (final person in _visible)
            Card(
              key: Key('person-${person.membershipId}'),
              child: ListTile(
                leading: CircleAvatar(
                  child: Icon(
                    person.isSupervisor
                        ? Icons.supervisor_account_outlined
                        : Icons.badge_outlined,
                  ),
                ),
                title: Text(person.displayName),
                subtitle: Text(
                  '${person.role == 'DRIVER' ? 'Operator' : 'Supervisor'} · ${person.phone}\n'
                  '${person.status}${person.sites.isEmpty ? '' : ' · ${person.sites.map((site) => site.name).join(', ')}'}',
                ),
                isThreeLine: true,
                onTap: () => _form(person),
                trailing: PopupMenuButton<String>(
                  onSelected: (action) =>
                      action == 'edit' ? _form(person) : _toggle(person),
                  itemBuilder: (_) => [
                    const PopupMenuItem(value: 'edit', child: Text('Edit')),
                    PopupMenuItem(
                      value: 'toggle',
                      child: Text(
                        person.isActive ? 'Deactivate' : 'Reactivate',
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _PersonForm extends StatefulWidget {
  const _PersonForm({required this.api, this.person});

  final OwnerPeopleSiteApi api;
  final OwnerPerson? person;

  @override
  State<_PersonForm> createState() => _PersonFormState();
}

class _PersonFormState extends State<_PersonForm> {
  late final TextEditingController _name;
  late final TextEditingController _phone;
  late String _role;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.person?.displayName);
    _phone = TextEditingController(text: widget.person?.phone);
    _role = widget.person?.role ?? 'DRIVER';
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty ||
        (widget.person == null && _phone.text.trim().isEmpty)) {
      setState(() => _error = 'Name and phone are required.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final input = OwnerPersonInput(
        displayName: _name.text.trim(),
        phone: _phone.text.trim(),
        role: _role,
      );
      if (widget.person == null) {
        await widget.api.inviteOwnerPerson(input);
      } else {
        await widget.api.updateOwnerPerson(widget.person!.membershipId, input);
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.person == null ? 'Invite person' : 'Edit person'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const Key('person-name'),
            controller: _name,
            decoration: const InputDecoration(labelText: 'Name'),
          ),
          TextField(
            key: const Key('person-phone'),
            controller: _phone,
            enabled: widget.person == null,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'Phone'),
          ),
          DropdownButtonFormField<String>(
            key: const Key('person-role'),
            initialValue: _role,
            decoration: const InputDecoration(labelText: 'Role'),
            items: const [
              DropdownMenuItem(value: 'DRIVER', child: Text('Operator')),
              DropdownMenuItem(value: 'SUPERVISOR', child: Text('Supervisor')),
            ],
            onChanged: widget.person == null || widget.person!.isInvited
                ? (value) => setState(() => _role = value!)
                : null,
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: _saving ? null : () => Navigator.pop(context),
        child: const Text('CANCEL'),
      ),
      FilledButton(
        key: const Key('save-person'),
        onPressed: _saving ? null : _save,
        child: Text(_saving ? 'SAVING…' : 'SAVE'),
      ),
    ],
  );
}

class OwnerSitesScreen extends StatefulWidget {
  const OwnerSitesScreen({
    required this.api,
    this.assetApi,
    this.onUnauthorized,
    super.key,
  });

  final OwnerPeopleSiteApi api;
  final OwnerAssetApi? assetApi;
  final OwnerUnauthorized? onUnauthorized;

  @override
  State<OwnerSitesScreen> createState() => _OwnerSitesScreenState();
}

class _OwnerSitesScreenState extends State<OwnerSitesScreen> {
  final _search = TextEditingController();
  List<OwnerManagedSite> _sites = const [];
  List<OwnerPerson> _people = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _search.addListener(_changed);
    _load();
  }

  @override
  void dispose() {
    _search
      ..removeListener(_changed)
      ..dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final values = await Future.wait([
        widget.api.ownerSites(),
        widget.api.ownerPeople(),
      ]);
      if (mounted) {
        setState(() {
          _sites = values[0] as List<OwnerManagedSite>;
          _people = values[1] as List<OwnerPerson>;
        });
      }
    } on ApiException catch (error) {
      if (error.isUnauthorized && widget.onUnauthorized != null) {
        await widget.onUnauthorized!();
      } else if (mounted) {
        setState(() => _error = error.message);
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<OwnerManagedSite> get _visible {
    final query = _search.text.trim().toLowerCase();
    return _sites.where((site) {
      return query.isEmpty ||
          site.name.toLowerCase().contains(query) ||
          (site.code?.toLowerCase().contains(query) ?? false);
    }).toList();
  }

  Future<void> _form([OwnerManagedSite? site]) async {
    final saved = await showDialog<bool>(
      context: context,
      builder: (_) => _SiteForm(api: widget.api, site: site),
    );
    if (saved == true) await _load();
  }

  Future<void> _details(OwnerManagedSite site) async {
    await Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => OwnerSiteDetailScreen(
          api: widget.api,
          assetApi: widget.assetApi,
          site: site,
          supervisors: _people
              .where((person) => person.isSupervisor && person.isActive)
              .toList(),
        ),
      ),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _load,
    child: ListView(
      key: const Key('owner-sites-list'),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'SITES',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            FilledButton.icon(
              key: const Key('add-site'),
              onPressed: () => _form(),
              icon: const Icon(Icons.add_location_alt_outlined),
              label: const Text('ADD SITE'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          children: [
            _CountChip(label: 'Total', count: _sites.length),
            _CountChip(
              label: 'Active',
              count: _sites.where((site) => site.isActive).length,
            ),
            _CountChip(
              label: 'Inactive',
              count: _sites.where((site) => !site.isActive).length,
            ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('site-search'),
          controller: _search,
          decoration: const InputDecoration(
            labelText: 'Search sites',
            prefixIcon: Icon(Icons.search),
          ),
        ),
        if (_loading) const LinearProgressIndicator(),
        if (_error != null) _ErrorCard(message: _error!, onRetry: _load),
        if (!_loading && _visible.isEmpty)
          const _EmptyCard(
            icon: Icons.location_off_outlined,
            text: 'No sites match this view.',
          ),
        for (final site in _visible)
          Card(
            key: Key('site-${site.id}'),
            child: ListTile(
              leading: const Icon(Icons.location_on_outlined),
              title: Text(site.name),
              subtitle: Text(
                '${site.code ?? 'No code'} · ${site.status}\n'
                '${site.supervisors.length} supervisors · ${site.assetCount} active assets',
              ),
              isThreeLine: true,
              onTap: () => _details(site),
              trailing: IconButton(
                tooltip: 'Edit site',
                onPressed: () => _form(site),
                icon: const Icon(Icons.edit_outlined),
              ),
            ),
          ),
      ],
    ),
  );
}

class _SiteForm extends StatefulWidget {
  const _SiteForm({required this.api, this.site});

  final OwnerPeopleSiteApi api;
  final OwnerManagedSite? site;

  @override
  State<_SiteForm> createState() => _SiteFormState();
}

class _SiteFormState extends State<_SiteForm> {
  late final TextEditingController _name;
  late final TextEditingController _code;
  late final TextEditingController _location;
  late final TextEditingController _latitude;
  late final TextEditingController _longitude;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final site = widget.site;
    _name = TextEditingController(text: site?.name);
    _code = TextEditingController(text: site?.code);
    _location = TextEditingController(text: site?.locationDescription);
    _latitude = TextEditingController(text: site?.latitude?.toString());
    _longitude = TextEditingController(text: site?.longitude?.toString());
  }

  @override
  void dispose() {
    _name.dispose();
    _code.dispose();
    _location.dispose();
    _latitude.dispose();
    _longitude.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty) {
      setState(() => _error = 'Site name is required.');
      return;
    }
    final latitude = _latitude.text.trim().isEmpty
        ? null
        : double.tryParse(_latitude.text.trim());
    final longitude = _longitude.text.trim().isEmpty
        ? null
        : double.tryParse(_longitude.text.trim());
    if ((_latitude.text.trim().isNotEmpty && latitude == null) ||
        (_longitude.text.trim().isNotEmpty && longitude == null)) {
      setState(() => _error = 'Coordinates must be valid numbers.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    final input = OwnerSiteInput(
      name: _name.text.trim(),
      code: _code.text.trim().isEmpty ? null : _code.text.trim(),
      locationDescription: _location.text.trim().isEmpty
          ? null
          : _location.text.trim(),
      latitude: latitude,
      longitude: longitude,
    );
    try {
      if (widget.site == null) {
        await widget.api.createOwnerSite(input);
      } else {
        await widget.api.updateOwnerSite(widget.site!.id, input);
      }
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.site == null ? 'Add site' : 'Edit site'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const Key('site-name'),
            controller: _name,
            decoration: const InputDecoration(labelText: 'Name'),
          ),
          TextField(
            key: const Key('site-code'),
            controller: _code,
            decoration: const InputDecoration(labelText: 'Code'),
          ),
          TextField(
            key: const Key('site-location'),
            controller: _location,
            decoration: const InputDecoration(
              labelText: 'Address or description',
            ),
          ),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _latitude,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(labelText: 'Latitude'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _longitude,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(labelText: 'Longitude'),
                ),
              ),
            ],
          ),
          if (_error != null)
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: _saving ? null : () => Navigator.pop(context),
        child: const Text('CANCEL'),
      ),
      FilledButton(
        key: const Key('save-site'),
        onPressed: _saving ? null : _save,
        child: Text(_saving ? 'SAVING…' : 'SAVE'),
      ),
    ],
  );
}

class OwnerSiteDetailScreen extends StatefulWidget {
  const OwnerSiteDetailScreen({
    required this.api,
    required this.site,
    required this.supervisors,
    this.assetApi,
    super.key,
  });

  final OwnerPeopleSiteApi api;
  final OwnerAssetApi? assetApi;
  final OwnerManagedSite site;
  final List<OwnerPerson> supervisors;

  @override
  State<OwnerSiteDetailScreen> createState() => _OwnerSiteDetailScreenState();
}

class _OwnerSiteDetailScreenState extends State<OwnerSiteDetailScreen> {
  late OwnerManagedSite _site;
  String? _selectedSupervisor;
  bool _saving = false;
  bool _loadingAssets = false;
  List<SiteDeployedAsset> _assets = const [];
  List<OwnerAsset> _deployableAssets = const [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _site = widget.site;
    _loadAssets();
  }

  Future<void> _loadAssets() async {
    final api = widget.assetApi;
    if (api == null) return;
    setState(() => _loadingAssets = true);
    try {
      final values = await Future.wait([
        api.ownerSiteAssets(_site.id),
        api.ownerAssets(status: 'ACTIVE'),
      ]);
      if (mounted) {
        setState(() {
          _assets = values[0] as List<SiteDeployedAsset>;
          _deployableAssets = (values[1] as List<OwnerAsset>)
              .where((asset) => asset.currentDeployment == null)
              .toList();
        });
      }
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loadingAssets = false);
    }
  }

  Future<void> _deployAsset() async {
    final api = widget.assetApi;
    if (api == null) return;
    final selected = await showDialog<OwnerAsset>(
      context: context,
      builder: (_) =>
          _DeployAssetToSiteDialog(assets: _deployableAssets, site: _site),
    );
    if (selected == null) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await api.deployOwnerAsset(selected.id, _site.id);
      await _loadAssets();
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  List<OwnerPerson> get _available => widget.supervisors
      .where(
        (person) => !_site.supervisors.any(
          (assigned) => assigned.membershipId == person.membershipId,
        ),
      )
      .toList();

  Future<void> _grant() async {
    if (_selectedSupervisor == null) return;
    await _action(
      () => widget.api.grantOwnerSiteSupervisor(_site.id, _selectedSupervisor!),
    );
    _selectedSupervisor = null;
  }

  Future<void> _revoke(String membershipId) async {
    await _action(
      () => widget.api.revokeOwnerSiteSupervisor(_site.id, membershipId),
    );
  }

  Future<void> _toggle() async {
    await _action(
      () => widget.api.setOwnerSiteActive(_site.id, !_site.isActive),
    );
  }

  Future<void> _action(Future<OwnerManagedSite> Function() action) async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final site = await action();
      if (mounted) setState(() => _site = site);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(_site.name)),
    body: ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('${_site.code ?? 'No code'} · ${_site.status}'),
        if (_site.locationDescription != null) Text(_site.locationDescription!),
        if (_site.latitude != null && _site.longitude != null)
          Text('${_site.latitude}, ${_site.longitude}'),
        const Divider(height: 32),
        Text('SUPERVISORS', style: Theme.of(context).textTheme.titleMedium),
        for (final supervisor in _site.supervisors)
          ListTile(
            title: Text(supervisor.displayName),
            trailing: IconButton(
              key: Key('remove-supervisor-${supervisor.membershipId}'),
              tooltip: 'Remove access',
              onPressed: _saving
                  ? null
                  : () => _revoke(supervisor.membershipId),
              icon: const Icon(Icons.remove_circle_outline),
            ),
          ),
        if (_site.isActive && _available.isNotEmpty)
          Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<String>(
                  key: const Key('site-supervisor'),
                  initialValue: _selectedSupervisor,
                  hint: const Text('Choose supervisor'),
                  items: _available
                      .map(
                        (person) => DropdownMenuItem(
                          value: person.membershipId,
                          child: Text(person.displayName),
                        ),
                      )
                      .toList(),
                  onChanged: (value) =>
                      setState(() => _selectedSupervisor = value),
                ),
              ),
              IconButton(
                key: const Key('grant-supervisor'),
                onPressed: _saving || _selectedSupervisor == null
                    ? null
                    : _grant,
                icon: const Icon(Icons.add_circle_outline),
              ),
            ],
          ),
        const Divider(height: 32),
        Row(
          children: [
            Expanded(
              child: Text(
                'ASSETS — ${_assets.length}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            if (widget.assetApi != null && _site.isActive)
              FilledButton.icon(
                key: const Key('deploy-site-asset'),
                onPressed:
                    _saving || _loadingAssets || _deployableAssets.isEmpty
                    ? null
                    : _deployAsset,
                icon: const Icon(Icons.add),
                label: const Text('DEPLOY ASSET'),
              ),
          ],
        ),
        if (_loadingAssets) const LinearProgressIndicator(),
        if (!_loadingAssets && _assets.isEmpty)
          const _EmptyCard(
            icon: Icons.precision_manufacturing_outlined,
            text: 'No assets are deployed to this Site.',
          ),
        for (final asset in _assets)
          ListTile(
            key: Key('site-asset-${asset.assetId}'),
            leading: const Icon(Icons.local_shipping_outlined),
            title: Text(asset.registrationNumber ?? asset.assetCode),
            subtitle: Text(
              '${asset.shortName ?? asset.assetCode}\n'
              'Driver: ${asset.driverName ?? 'Unassigned'}',
            ),
            isThreeLine: true,
          ),
        if (_error != null) _ErrorCard(message: _error!, onRetry: () async {}),
        const SizedBox(height: 24),
        OutlinedButton.icon(
          key: const Key('toggle-site-status'),
          onPressed: _saving ? null : _toggle,
          icon: Icon(_site.isActive ? Icons.block : Icons.restore),
          label: Text(_site.isActive ? 'DEACTIVATE SITE' : 'REACTIVATE SITE'),
        ),
      ],
    ),
  );
}

class _DeployAssetToSiteDialog extends StatefulWidget {
  const _DeployAssetToSiteDialog({required this.assets, required this.site});

  final List<OwnerAsset> assets;
  final OwnerManagedSite site;

  @override
  State<_DeployAssetToSiteDialog> createState() =>
      _DeployAssetToSiteDialogState();
}

class _DeployAssetToSiteDialogState extends State<_DeployAssetToSiteDialog> {
  String? _selected;

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('DEPLOY ASSET'),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Site: ${widget.site.name}'),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('site-deploy-asset-selector'),
          initialValue: _selected,
          decoration: const InputDecoration(
            labelText: 'Active undeployed asset',
          ),
          items: widget.assets
              .map(
                (asset) => DropdownMenuItem(
                  value: asset.id,
                  child: Text(
                    '${asset.assetCode} / '
                    '${asset.registrationNumber ?? asset.shortName ?? asset.assetCode}',
                  ),
                ),
              )
              .toList(),
          onChanged: (value) => setState(() => _selected = value),
        ),
      ],
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('CANCEL'),
      ),
      FilledButton(
        key: const Key('confirm-site-deploy'),
        onPressed: _selected == null
            ? null
            : () => Navigator.pop(
                context,
                widget.assets.firstWhere((asset) => asset.id == _selected),
              ),
        child: const Text('DEPLOY'),
      ),
    ],
  );
}

class _CountChip extends StatelessWidget {
  const _CountChip({required this.label, required this.count});
  final String label;
  final int count;

  @override
  Widget build(BuildContext context) => Chip(label: Text('$label  $count'));
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.onRetry});
  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: ListTile(
      title: Text(message),
      trailing: TextButton(onPressed: onRetry, child: const Text('RETRY')),
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
      padding: const EdgeInsets.all(24),
      child: Column(
        children: [Icon(icon), const SizedBox(height: 8), Text(text)],
      ),
    ),
  );
}
